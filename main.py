import boto3
import os
from pprint import pprint
from botocore.exceptions import ClientError

KEY_PAIR_NAME = "TeraKey"
SECURITY_GROUP_NAME = "TeraSecurityGroup"
TARGET_GROUP_NAME = "TeraTargetGroup"
LOAD_BALANCER_NAME = "TeraLoadBalancer"
IMAGE_NAME = "TeraImage"

WEBSERVER_PORT = 5000

client = boto3.client('ec2')
ec2 = boto3.resource('ec2')
elbv2 = boto3.client('elbv2')
autoscaling = boto3.client('autoscaling')


def terminate_instances():
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

        # terminated = False
        # while(not terminated):
        #     ids = []
        #     states = []
        #     terminated = True

        #     response = client.describe_instances(
        #         Filters=[
        #             {
        #                 'Name': 'tag:Owner',
        #                 'Values': [
        #                     'Tera',
        #                 ]
        #             }
        #         ]
        #     )
        #     for i in response["Reservations"]:
        #         ids.append(i["Instances"][0]["InstanceId"])
        #         states.append(i["Instances"][0]["State"]["Name"])

        #     for i in range(len(ids)):
        #         if states[i] != "terminated":
        #             terminated = False

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

def delete_security_group():

    try:
        response = client.describe_security_groups(
            GroupNames=[SECURITY_GROUP_NAME])
        try:
            response = client.delete_security_group(
                GroupName=SECURITY_GROUP_NAME)
            print('Security Group Deleted')
        except ClientError as e:
            print(e)
    except ClientError as e:
        print(e)

def create_security_group():
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
        InstanceType="t2.micro",
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
                    cd Mini_REST_Tasks/
                    uvicorn main:app --reload --host "0.0.0.0" --port 5000
                        '''
    )
    print("Instances Created")
    instance_ids = []
    for instance in instances:
        instance_ids.append(instance.id)
    waiter = client.get_waiter('instance_running')
    waiter.wait(InstanceIds = instance_ids)
    print("Instances Running")

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
        TargetType='instance'
    )
    print("Target Group Created")

def delete_load_balancer():
    try:
        response = elbv2.describe_load_balancers(Names=[LOAD_BALANCER_NAME])
        arn = response['LoadBalancers'][0]['LoadBalancerArn']
        try:
            response = elbv2.delete_load_balancer(LoadBalancerArn=arn)
            waiter = elbv2.get_waiter('load_balancers_deleted')
            waiter.wait(LoadBalancerArns = [arn])
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
    print("Image Created")
    waiter = client.get_waiter('image_available')
    waiter.wait(ImageIds= [response['ImageId']])
    print("Image Available")

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

def main():
    terminate_instances()
    delete_load_balancer()
    delete_target_group()
    deregister_image()
    delete_key_pair()
    create_key_pair()
    delete_security_group()
    create_security_group()
    create_instance()
    create_image()
    create_load_balancer()
    create_target_group()



main()
# print(client.waiter_names)
