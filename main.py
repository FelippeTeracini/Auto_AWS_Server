import boto3
from botocore.exceptions import ClientError

KEY_PAIR_NAME = "TeraKey"
SECURITY_GROUP_NAME = "TeraSecurityGroup"

client = boto3.client('ec2')
ec2 = boto3.resource('ec2')


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

        terminated = False
        while(not terminated):
            ids = []
            states = []
            terminated = True

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
            for i in response["Reservations"]:
                ids.append(i["Instances"][0]["InstanceId"])
                states.append(i["Instances"][0]["State"]["Name"])

            for i in range(len(ids)):
                if states[i] != "terminated":
                    terminated = False
        print("Instance terminated")

    except ClientError as e:
        print(e)


def create_and_delete_key_pair():
    try:
        response = client.describe_key_pairs(KeyNames=[KEY_PAIR_NAME])
        try:
            response = client.delete_key_pair(KeyName=KEY_PAIR_NAME)
            print('Key Pair Deleted')
        except ClientError as e:
            print(e)
    except ClientError as e:
        print(e)

    response = client.create_key_pair(KeyName=KEY_PAIR_NAME)
    key_file = open('TeraKey.pem', 'w+')
    key_file.write(response['KeyMaterial'])
    key_file.close()


def create_and_delete_security_group():
    response = client.describe_vpcs()
    vpc_id = response.get('Vpcs', [{}])[0].get('VpcId', '')

    try:
        response = client.describe_security_groups(
            GroupNames=[SECURITY_GROUP_NAME])
        print(response)
        try:
            response = client.delete_security_group(
                GroupName=SECURITY_GROUP_NAME)
            print('Security Group Deleted')
        except ClientError as e:
            print(e)
    except ClientError as e:
        print(e)

    try:
        response = client.create_security_group(GroupName=SECURITY_GROUP_NAME,
                                                Description='Teras security group',
                                                VpcId=vpc_id)
        security_group_id = response['GroupId']
        print('Security Group Created %s in vpc %s.' %
              (security_group_id, vpc_id))

        data = client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp',
                    'FromPort': 5000,
                    'ToPort': 5000,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        print('Ingress Successfully Set %s' % data)
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
                    uvicorn main:app --reload --host 0.0.0.0 --port 5000
                        '''
    )


def main():
    terminate_instances()
    create_and_delete_key_pair()
    create_and_delete_security_group()
    create_instance()


main()
