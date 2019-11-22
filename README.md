# Auto_AWS_Server
Auto setup for a webserver infrasctructure in AWS using boto3

## How to Run

### Configuring and Installing AWS CLI

If you have pip installed and a compatible version of python, you can install AWS CLI using the following command:
```bash
$ pip3 install awscli --upgrade --user
```
To configure AWS CLI run the command aws configure:
```bash
$ aws configure
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-east-1
Default output format [None]: json
```

### Launching the Infrastructure

To launch your infrastructure run the following command:
```bash
$ python3 main.py
```

### Using the client

Wait for all the steps to be completed (It can take a while). Then, go to the AWS EC2 management console and get your newly created loadbalancer's DNS. Access the following address on any browser to use the client:
```bash
http://<YOURDNS>:<PORT (DEFAULT=5000)>/docs
```
