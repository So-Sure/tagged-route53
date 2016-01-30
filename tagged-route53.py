#!/usr/bin/python
import requests
import boto3
import argparse

class Dns(object):

    # Default constructor of the class.
    def __init__(self):
        self.ec2_client = boto3.client('ec2')
        self.dns_client = boto3.client('route53')
        self.role = None
        self.env = None
        self.instance_id = None
        self.instance_count = None
        self.hostname = None
        self.ip = None
        self.domain = None
        self.tag_env = None
        self.tag_role = None
        self.tag_instance_id = None

    def current_instance(self):
        response = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
        self.instance_id = response.text
        print 'Instance: %s' % (self.instance_id)

    def current_ip(self):
        response = requests.get('http://169.254.169.254/latest/meta-data/local-ipv4')
        self.ip = response.text
        print 'IP: %s' % (self.ip)

    def current_role_env(self):
        if self.instance_id is None:
            self.current_instance()
        response = self.ec2_client.describe_instances(InstanceIds=[self.instance_id])
        instances = response['Reservations']
        # Only 1 instance
        tags = instances[0]['Instances'][0]['Tags']
        for tag in tags:
            if tag['Key'] == self.tag_env:
                self.env = tag['Value']
            elif tag['Key'] == self.tag_role:
                self.role = tag['Value']

        print 'Env: %s Role: %s' % (self.env, self.role)

    def get_instance_count(self):
        if self.env is None or self.role is None:
            self.current_role_env()
        filters = [
            { 'Name':'tag:%s' % (self.tag_env), 'Values':[self.env]},
            { 'Name':'tag:%s' % (self.tag_role), 'Values':[self.role]}
        ]
        response = self.ec2_client.describe_instances(Filters=filters)
        instances = response['Reservations']
        instance_ids = []
        for instance in instances:
            if instance['Instances'][0]['State']['Name'] == 'running':
                tags = instance['Instances'][0]['Tags']
                for tag in tags:
                    if tag['Key'] == self.tag_instance_id:
                        instance_ids.append(tag['Value'])

        # the current instance will be in the list, but as we want to start at 1, that's good
        self.instance_count = len(instances)
        print 'Instance count: %d' % (self.instance_count)

        # May be replacing a previous server
        for i in range(1, self.instance_count + 1):
            if str(i) not in instance_ids:
                self.instance_count = i
                break

        print 'Using Instance id: %d' % (self.instance_count)
        self.ec2_client.create_tags(
            Resources=[self.instance_id],
            Tags=[{'Key': self.tag_instance_id, 'Value': str(self.instance_count) }]
        )

    def get_hostname(self):
        if self.instance_count is None:
            self.get_instance_count()
        self.hostname = '%s-%d.%s.%s' % (self.role, self.instance_count, self.env, self.domain)
        print 'Hostname: %s' % (self.hostname)

    def update_dns(self):
        if self.hostname is None:
            self.get_hostname()
        if self.ip is None:
            self.current_ip()

        response = self.dns_client.list_hosted_zones_by_name(
            DNSName=self.domain
        )
        zone_id = response['HostedZones'][0]['Id'].replace('/hostedzone/', '')
        response = self.dns_client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch={
                'Changes': [
                    {
                        'Action': 'UPSERT',
                        'ResourceRecordSet': {
                            'Name': self.hostname,
                            'Type': 'A',
                            'TTL': 60,
                            'ResourceRecords': [
                                {
                                    'Value': self.ip
                                },
                            ]
                        }
                    },
                ]
            }
        )
        print response

    def main(self):
        parser = argparse.ArgumentParser(description='Update route 53 dns based on server tags')
        parser.add_argument('domain', help='Domain name')
        parser.add_argument('--tag-role', default='role', help='Role tag name (default: %(default)s)')
        parser.add_argument('--tag-env', default='env', help='Environment tag name (default: %(default)s)')
        parser.add_argument('--tag-instance-id', default='instance-id', help='Instance Id tag name (default: %(default)s)')
        args = parser.parse_args()
        
        self.domain = args.domain
        self.tag_env = args.tag_env
        self.tag_role = args.tag_role
        self.tag_instance_id = args.tag_instance_id

        self.update_dns()

if __name__ == '__main__':

    launcher = Dns()
    launcher.main()

