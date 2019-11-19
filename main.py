import boto3
import os
import time
from pprint import pprint
from botocore.exceptions import ClientError

KEY_PAIR_NAME = "TeraKey"
SECURITY_GROUP_NAME = "TeraSecurityGroup"
TARGET_GROUP_NAME = "TeraTargetGroup"
LOAD_BALANCER_NAME = "TeraLoadBalancer"
IMAGE_NAME = "TeraImage"
LAUNCH_CONFIGURATION_NAME = "TeraLaunchConfiguration"
AUTOSCALING_NAME = "TeraAutoscaling"

SECURITY_GROUP_NAME_OHIO = "TeraSecurityGroupOhio"

MIN_AUTOSCALING_SIZE = 1
MAX_AUTOSCALING_SIZE = 3

NORTH_VIRGINIA = 'us-east-1'
OHIO = 'us-east-2'

INSTANCE_TYPE = "t2.micro"

WEBSERVER_PORT = 5000

client = boto3.client('ec2', region_name=NORTH_VIRGINIA)
ec2 = boto3.resource('ec2', region_name=NORTH_VIRGINIA)
elbv2 = boto3.client('elbv2', region_name=NORTH_VIRGINIA)
autoscaling = boto3.client('autoscaling', region_name=NORTH_VIRGINIA)

client_ohio = boto3.client('ec2', region_name=OHIO)
ec2_ohio = boto3.resource('ec2', region_name=OHIO)

def terminate_instances(client, ec2):
    try:
        response = client.describe_instances(
            Filters=[
                {
                    'Name': 'tag:Owner',
                    'Values': [
                        'Tera',
                    ]
                }
            ]
        )

        ids = []
        states = []

        for i in response["Reservations"]:
            ids.append(i["Instances"][0]["InstanceId"])
            states.append(i["Instances"][0]["State"]["Name"])

        for i in range(len(ids)):
            if states[i] != "terminated":
                ec2.instances.filter(InstanceIds=[ids[i]]).terminate()
                print("Instance deleted")

        if(len(ids)) <= 0:
            print("Sem instancias")
            return
        waiter = client.get_waiter('instance_terminated')
        waiter.wait(
            Filters = [{
                'Name':'tag:Owner',
                'Values': [
                    'Tera'
                ]
            }]
        )
        
        print("Instance terminated")

    except ClientError as e:
        print(e)

def delete_key_pair():
    try:
        response = client.describe_key_pairs(KeyNames=[KEY_PAIR_NAME])
        try:
            response = client.delete_key_pair(KeyName=KEY_PAIR_NAME)
            print('Key Pair Deleted')
        except ClientError as e:
            print(e)
    except ClientError as e:
        print(e)

def create_key_pair():
    response = client.create_key_pair(KeyName=KEY_PAIR_NAME)
    try:
        os.remove("TeraKey.pem")
    except ClientError as e:
        print(e)
    key_file = open('TeraKey.pem', 'w+')
    key_file.write(response['KeyMaterial'])
    key_file.close()
    os.chmod("TeraKey.pem", 0o400)
    print("Key Pair Created")

def delete_security_group(security_group_name, client):

    try:
        response = client.describe_security_groups(
            GroupNames=[security_group_name])
        try:
            response = client.delete_security_group(
                GroupName=security_group_name)
            print('Security Group Deleted')
        except ClientError as e:
            print(e)
    except ClientError as e:
        print(e)

def create_security_group(client):
    response = client.describe_vpcs()
    vpc_id = response.get('Vpcs', [{}])[0].get('VpcId', '')

    try:
        response = client.create_security_group(GroupName=SECURITY_GROUP_NAME,
                                                Description='Teras security group',
                                                VpcId=vpc_id)
        security_group_id = response['GroupId']
        print('Security Group Created')

        data = client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp',
                    'FromPort': WEBSERVER_PORT,
                    'ToPort': WEBSERVER_PORT,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        print('Ingress Successfully Set')
    except ClientError as e:
        print(e)

def create_instance():
    instances = ec2.create_instances(
        ImageId='ami-04b9e92b5572fa0d1',
        MinCount=1,
        MaxCount=1,
        SecurityGroups=[SECURITY_GROUP_NAME],
        KeyName=KEY_PAIR_NAME,
        InstanceType=INSTANCE_TYPE,
        TagSpecifications=[{'ResourceType': 'instance',
                            'Tags': [{'Key': 'Owner', 'Value': 'Tera'}, {'Key': 'Name', 'Value': 'TeraWebserverProjeto'}]}],
        UserData='''#! /bin/bash
                sudo apt-get update
                sudo apt-get -y install python3-pip
                pip3 install fastapi
                pip3 install uvicorn
                pip3 install pydantic
                cd home/ubuntu
                git clone https://github.com/FelippeTeracini/Mini_REST_Tasks.git
                cd Mini_REST_Tasks
                uvicorn main:app --reload --host "0.0.0.0" --port {}
                        '''.format(WEBSERVER_PORT)
    )
    print("Instances Created")
    instance_ids = []
    for instance in instances:
        instance_ids.append(instance.id)
    response = client.describe_instances(
        InstanceIds=[
        instance_ids[0],
        ]
    )
    waiter = client.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds = instance_ids)
    print("Instances Running and Status OK")
    return response['Reservations'][0]['Instances'][0]['PublicIpAddress']

def delete_target_group():   
    try:
        response = elbv2.describe_target_groups(Names=[TARGET_GROUP_NAME])
        arn = response['TargetGroups'][0]['TargetGroupArn']
        try:
            response = elbv2.delete_target_group(TargetGroupArn=arn)
            print("Target Group Deleted")
        except ClientError as e:
            print(e)
    except ClientError as e:
        print(e)

def create_target_group():
    response = client.describe_vpcs()
    vpc_id = response.get('Vpcs', [{}])[0].get('VpcId', '')

    response = elbv2.create_target_group(
        Name=TARGET_GROUP_NAME,
        Protocol='HTTP',
        Port=WEBSERVER_PORT,
        VpcId=vpc_id,
        TargetType='instance',
        HealthCheckEnabled=True
    )
    arn = response['TargetGroups'][0]['TargetGroupArn']
    print("Target Group Created")
    return arn

def delete_load_balancer():
    try:
        response = elbv2.describe_load_balancers(Names=[LOAD_BALANCER_NAME])
        arn = response['LoadBalancers'][0]['LoadBalancerArn']
        try:
            response = elbv2.delete_load_balancer(LoadBalancerArn=arn)
            waiter = elbv2.get_waiter('load_balancers_deleted')
            waiter.wait(LoadBalancerArns = [arn])
            time.sleep(30)
            print("Load Balancer Deleted")
        except ClientError as e:
            print(e)
    except ClientError as e:
            print(e)

def create_load_balancer():

    response = client.describe_security_groups(
            GroupNames=[SECURITY_GROUP_NAME])
    security_group_id = response['SecurityGroups'][0]['GroupId']

    response = elbv2.create_load_balancer(
        Name=LOAD_BALANCER_NAME,
        Subnets=[
            'subnet-5287350e',
            'subnet-82d868e5',
            'subnet-1965d937',
            'subnet-e189c8ab',
            'subnet-c2a760fc',
            'subnet-7e037471'
        ],
        Type = 'application',
        SecurityGroups=[
            security_group_id,
        ],
        Tags=[
            {
                'Key': 'Owner',
                'Value': 'Tera'
            },
        ]
    )
    arn = response['LoadBalancers'][0]['LoadBalancerArn']
    print("Load Balancer Created")
    waiter = elbv2.get_waiter('load_balancer_available')
    waiter.wait(LoadBalancerArns = [arn])
    print("Load Balancer Available")

    return arn

def create_image():

    instance_id = ""

    response = client.describe_instances(
            Filters=[
                {
                    'Name': 'tag:Owner',
                    'Values': [
                        'Tera'
                    ]
                }
            ]
        )

    for i in response["Reservations"]:
        if(i["Instances"][0]["State"]["Name"] != "terminated"):
            instance_id = i["Instances"][0]["InstanceId"]

    response = client.create_image(InstanceId=instance_id, Name=IMAGE_NAME)
    image_id = response['ImageId']
    print("Image Created")
    waiter = client.get_waiter('image_available')
    waiter.wait(ImageIds= [image_id])
    print("Image Available")
    return image_id

def deregister_image():
    try:
        response = client.describe_images(Filters=[
            {
                'Name': 'name',
                'Values': [
                 IMAGE_NAME
                ]
            },
        ])
        try:
            if(len(response['Images']) > 0):
                client.deregister_image(ImageId = response['Images'][0]['ImageId'])
                print("Image Deregistered")
        except ClientError as e:
            print(e)
    except ClientError as e:
            print(e)

def create_listener(lb_arn, tg_arn):
    response = elbv2.create_listener(
        LoadBalancerArn = lb_arn,
        Protocol = "HTTP",
        Port = WEBSERVER_PORT,
        DefaultActions = [{
            "Type":"forward",
            "TargetGroupArn":tg_arn
        }]
    )
    print("Listener Created")

def create_launch_configuration(image_id):
    response = autoscaling.create_launch_configuration(
        LaunchConfigurationName=LAUNCH_CONFIGURATION_NAME,
        ImageId=image_id,
        KeyName=KEY_PAIR_NAME,
        SecurityGroups=[SECURITY_GROUP_NAME],
        InstanceType = INSTANCE_TYPE,
        InstanceMonitoring={'Enabled': True},
        UserData = '''#!/bin/bash
                    cd home/ubuntu/Mini_REST_Tasks
                    uvicorn main:app --reload --host "0.0.0.0" --port {}
        '''.format(WEBSERVER_PORT)
    )
    print("Launch Configuration Created")

def create_launch_configuration2(server_address):
    response = autoscaling.create_launch_configuration(
        LaunchConfigurationName=LAUNCH_CONFIGURATION_NAME,
        ImageId='ami-04b9e92b5572fa0d1',
        KeyName=KEY_PAIR_NAME,
        SecurityGroups=[SECURITY_GROUP_NAME],
        InstanceType = INSTANCE_TYPE,
        InstanceMonitoring={'Enabled': True},
        UserData = '''#! /bin/bash
                    sudo apt-get update
                    sudo apt-get -y install python3-pip
                    pip3 install fastapi
                    pip3 install uvicorn
                    pip3 install pydantic
                    cd home/ubuntu
                    git clone https://github.com/FelippeTeracini/Mini_REST_Tasks.git
                    cd Mini_REST_Tasks
                    python3 redirection.py --server_address {} --port {}
        '''.format(server_address, WEBSERVER_PORT)
    )
    print("Launch Configuration Created")
    
def delete_launch_configuration():
    try:
        response = autoscaling.delete_launch_configuration(LaunchConfigurationName=LAUNCH_CONFIGURATION_NAME)
        print("Launch Configuration Deleted")
    except ClientError as e:
        print(e)

def create_autoscaling(tg_arn):
    response = autoscaling.create_auto_scaling_group(
        AutoScalingGroupName=AUTOSCALING_NAME,
        LaunchConfigurationName=LAUNCH_CONFIGURATION_NAME,
        MinSize=MIN_AUTOSCALING_SIZE,
        MaxSize=MAX_AUTOSCALING_SIZE,
        DefaultCooldown = 20,
        DesiredCapacity=MIN_AUTOSCALING_SIZE,
        AvailabilityZones=[
            'us-east-1a',
            'us-east-1b',
            'us-east-1c',
            'us-east-1d',
            'us-east-1e',
            'us-east-1f',
        ],
        TargetGroupARNs=[
            tg_arn,
        ],
        Tags=[
            {
                'Key': 'tag:Owner',
                'Value': 'Tera'
            }
        ]
    )
    print("Autoscaling Created")

def delete_autoscaling():
    try:
        response = autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=AUTOSCALING_NAME,
            MinSize=0,
            MaxSize=0,
            DesiredCapacity=0,
        )
        print("Autoscaling Updated")
        response = autoscaling.delete_auto_scaling_group(
            AutoScalingGroupName=AUTOSCALING_NAME,
            ForceDelete=True
        )
        print("Autoscaling Deleted")
        deleted = False
        while(not deleted):
            response = autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[
                    AUTOSCALING_NAME
                ]
            )
            if(len(response['AutoScalingGroups']) <= 0):
                deleted = True
        print("Autoscaling and Instances Deleted")
    except ClientError as e:
        print(e)

def create_instance_database():
    instances = ec2_ohio.create_instances(
        ImageId='ami-04b9e92b5572fa0d1',
        MinCount=1,
        MaxCount=1,
        SecurityGroups=[SECURITY_GROUP_NAME_OHIO],
        KeyName=KEY_PAIR_NAME,
        InstanceType=INSTANCE_TYPE,
        TagSpecifications=[{'ResourceType': 'instance',
                            'Tags': [{'Key': 'Owner', 'Value': 'Tera'}, {'Key': 'Name', 'Value': 'TeraMongo'}]}],
        UserData='''#! /bin/bash
                sudo apt-get update -y
                sudo apt-get install gnupg
                wget -qO - https://www.mongodb.org/static/pgp/server-4.2.asc | sudo apt-key add -
                echo "deb [ arch=amd64 ] https://repo.mongodb.org/apt/ubuntu bionic/mongodb-org/4.2 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-4.2.list
                sudo apt-get install -y mongodb-org
                echo "mongodb-org hold" | sudo dpkg --set-selections
                echo "mongodb-org-server hold" | sudo dpkg --set-selections
                echo "mongodb-org-shell hold" | sudo dpkg --set-selections
                echo "mongodb-org-mongos hold" | sudo dpkg --set-selections
                echo "mongodb-org-tools hold" | sudo dpkg --set-selections
                sudo service mongod start
                        '''
    )
    print("Instance TeraMongo Created")
    instance_ids = []
    for instance in instances:
        instance_ids.append(instance.id)
    response = client_ohio.describe_instances(
        InstanceIds=[
        instance_ids[0],
        ]
    )
    waiter = client_ohio.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds = instance_ids)
    print("Instances Running and Status OK")
    return response['Reservations'][0]['Instances'][0]['PrivateIpAddress']

def create_instance_web_mongo(server_address):
    instances = ec2_ohio.create_instances(
        ImageId='ami-04b9e92b5572fa0d1',
        MinCount=1,
        MaxCount=1,
        SecurityGroups=[SECURITY_GROUP_NAME],
        KeyName=KEY_PAIR_NAME,
        InstanceType=INSTANCE_TYPE,
        TagSpecifications=[{'ResourceType': 'instance',
                            'Tags': [{'Key': 'Owner', 'Value': 'Tera'}, {'Key': 'Name', 'Value': 'TeraWebMongo'}]}],
        UserData='''#! /bin/bash
                sudo apt-get update
                sudo apt-get -y install python3-pip
                pip3 install fastapi
                pip3 install uvicorn
                pip3 install pydantic
                pip3 install pymongo
                cd home/ubuntu
                git clone https://github.com/FelippeTeracini/Mini_REST_Tasks.git
                cd Mini_REST_Tasks
                uvicorn main:app --reload --host "0.0.0.0" --port {}
                        '''.format(WEBSERVER_PORT)
    )
    print("Instance TeraWebMongo Created")
    instance_ids = []
    for instance in instances:
        instance_ids.append(instance.id)
    response = client_ohio.describe_instances(
        InstanceIds=[
        instance_ids[0],
        ]
    )
    waiter = client_ohio.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds = instance_ids)
    print("Instances Running and Status OK")
    return response['Reservations'][0]['Instances'][0]['PublicIpAddress']

def create_security_group_ohio(client):
    response = client.describe_vpcs()
    vpc_id = response.get('Vpcs', [{}])[0].get('VpcId', '')

    try:
        response = client.create_security_group(GroupName=SECURITY_GROUP_NAME_OHIO,
                                                Description='Teras security group ohio',
                                                VpcId=vpc_id)
        security_group_id = response['GroupId']
        print('Security Group Ohio Created')

        data = client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp',
                    'FromPort': '27017',
                    'ToPort': '27017',
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        print('Ingress Ohio Successfully Set')
    except ClientError as e:
        print(e)

def create_instance_middleWeb(server_address):
    instances = ec2.create_instances(
        ImageId='ami-04b9e92b5572fa0d1',
        MinCount=1,
        MaxCount=1,
        SecurityGroups=[SECURITY_GROUP_NAME],
        KeyName=KEY_PAIR_NAME,
        InstanceType=INSTANCE_TYPE,
        TagSpecifications=[{'ResourceType': 'instance',
                            'Tags': [{'Key': 'Owner', 'Value': 'Tera'}, {'Key': 'Name', 'Value': 'TeraWebMiddle'}]}],
        UserData = '''#! /bin/bash
                sudo apt-get update
                sudo apt-get -y install python3-pip
                pip3 install fastapi
                pip3 install uvicorn
                pip3 install pydantic
                cd home/ubuntu
                git clone https://github.com/FelippeTeracini/Mini_REST_Tasks.git
                cd Mini_REST_Tasks
                python3 redirection.py --server_address {} --port {}
        '''.format(server_address, WEBSERVER_PORT)
    )
    print("Instance TeraWebMiddle Created")
    instance_ids = []
    for instance in instances:
        instance_ids.append(instance.id)
    response = client.describe_instances(
        InstanceIds=[
        instance_ids[0],
        ]
    )
    waiter = client.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds = instance_ids)
    print("Instances Running and Status OK")
    return response['Reservations'][0]['Instances'][0]['PublicIpAddress']

def main2():
    print("----- MAIN -----")
    delete_autoscaling()
    terminate_instances()
    delete_load_balancer()
    delete_target_group()
    deregister_image()
    delete_key_pair()
    create_key_pair()
    delete_security_group()
    delete_launch_configuration()
    create_security_group()
    create_instance()
    image_id = create_image()
    terminate_instances()
    lb_arn = create_load_balancer()
    tg_arn = create_target_group()
    create_listener(lb_arn, tg_arn)
    create_launch_configuration(image_id)
    create_autoscaling(tg_arn)

def create_north_virginia(server_address):
    print("----- create_north_virginia-----")
    delete_autoscaling()
    terminate_instances(client, ec2)
    delete_load_balancer()
    delete_target_group()
    delete_key_pair()
    create_key_pair()
    delete_launch_configuration()
    delete_security_group(SECURITY_GROUP_NAME, client)
    create_security_group(client)
    ip_middle_web = create_instance_middleWeb(server_address)
    lb_arn = create_load_balancer()
    tg_arn = create_target_group()
    create_listener(lb_arn, tg_arn)
    create_launch_configuration2(ip_middle_web)
    create_autoscaling(tg_arn)

def create_ohio():
    print("----- create_ohio-----")
    terminate_instances(client_ohio, ec2_ohio)
    delete_security_group(SECURITY_GROUP_NAME_OHIO, client_ohio)
    create_security_group_ohio(client_ohio)
    ip_db = create_instance_database()
    ip_web_mongo = create_instance_web_mongo(ip_db)
    return ip_web_mongo

def main():
    ip_web_mongo = create_ohio()
    create_north_virginia(ip_web_mongo)

def delete_all():
    delete_autoscaling()
    terminate_instances()
    delete_load_balancer()
    delete_target_group()
    deregister_image()
    delete_key_pair()
    delete_security_group()
    delete_launch_configuration()

def create_test_instance():
    create_instance()

# create_test_instance()
create_north_virginia('http://3.88.204.96')
# print(autoscaling.waiter_names)
# print(client.waiter_names)
# main()
