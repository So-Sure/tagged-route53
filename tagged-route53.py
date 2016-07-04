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
        self.instances = None
        self.indexes = None
        self.instance_count = None
        self.hostname = None
        self.ip = None
        self.use_public_ip = None
        self.domain = None
        self.set_tag_name = True
        self.set_dns_registration = True
        self.tag_env = None
        self.tag_role = None
        self.tag_index = None
        self.name = None
        self.update_dns = True
        self.quiet = False

    def current_instance(self):
        response = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
        self.instance_id = response.text
        if not self.quiet:
            print 'Instance: %s' % (self.instance_id)

    def current_public_ip(self):
        response = self.ec2_client.describe_instances(InstanceIds=[self.instance_id])
        instances = response['Reservations']
        self.ip = instances[0]['Instances'][0]['PublicIpAddress']
        if not self.quiet:
            print 'IP: %s' % (self.ip)

    def current_private_ip(self):
        response = self.ec2_client.describe_instances(InstanceIds=[self.instance_id])
        instances = response['Reservations']
        self.ip = instances[0]['Instances'][0]['PrivateIpAddress']
        if not self.quiet:
            print 'IP: %s' % (self.ip)

    def current_role_env(self):
        if self.instance_id is None:
            self.current_instance()
        response = self.ec2_client.describe_instances(InstanceIds=[self.instance_id])
        instances = response['Reservations']
        # Only 1 instance
        tags = instances[0]['Instances'][0]['Tags']
        for tag in tags:
            if self.env is None and tag['Key'] == self.tag_env:
                self.env = tag['Value']
            elif self.role is None and tag['Key'] == self.tag_role:
                self.role = tag['Value']

        if not self.quiet:
            print 'Env: %s Role: %s' % (self.env, self.role)

    def get_instance_ids(self):
        if self.env is None or self.role is None:
            self.current_role_env()
        filters = [
            { 'Name':'tag:%s' % (self.tag_env), 'Values':[self.env]},
            { 'Name':'tag:%s' % (self.tag_role), 'Values':[self.role]}
        ]
        response = self.ec2_client.describe_instances(Filters=filters)
        instances = response['Reservations']

        if not self.quiet:
            print 'Checking tags'
        self.instances = {}
        self.indexes = []
        for instance in instances:
            index = -1
            if instance['Instances'][0]['State']['Name'] == 'running':
                instance_id = instance['Instances'][0]['InstanceId']
                tags = instance['Instances'][0]['Tags']
                for tag in tags:
                    if tag['Key'] == self.tag_index:
                        index = tag['Value']                
                        self.indexes.append(index)
                self.instances[instance_id] = int(index)

    def get_instance_count(self):
        if self.instances is None:
            self.get_instance_ids()

        # the current instance will be in the list, but as we want to start at 1, that's good
        self.instance_count = len(self.instances)
        if not self.quiet:
            print 'Instance count: %d' % (self.instance_count)

        if self.instances.has_key(self.instance_id) and self.instances[self.instance_id] >= 0:
            self.instance_count = self.instances[self.instance_id]
            if not self.quiet:
                print 'Index is already set %s' % (self.instance_count)
            self.update_dns = False
            return

        if self.instance_count < 1:
            raise Exception('Instance count must be 1 or more')

        if not self.quiet:
            print self.indexes

        # May be replacing a previous server
        for i in range(1, self.instance_count + 2):
            if str(i) not in self.indexes:
                self.instance_count = i
                break

        if not self.quiet:
            print 'Using index: %d' % (self.instance_count)
        self.ec2_client.create_tags(
            Resources=[self.instance_id],
            Tags=[{'Key': self.tag_index, 'Value': str(self.instance_count) }]
        )

        if self.set_tag_name:
            name = '%s-%s-%d' % (self.env, self.role, self.instance_count)
            if not self.quiet:
                print 'Setting instance name: %s' % (name)
            self.ec2_client.create_tags(
                Resources=[self.instance_id],
                Tags=[{'Key': 'Name', 'Value': name }]
            )

    def get_hostname(self):
        if self.instance_count is None:
            self.get_instance_count()

        if self.name is None:
            self.hostname = '%s-%d.%s.%s' % (self.role, self.instance_count, self.env, self.domain)
        else:
            self.hostname = "%s.%s" % (self.name, self.domain)

        if not self.quiet:
            print 'Hostname: %s' % (self.hostname)
        else:
            print self.hostname

    def run_update_all(self):
        self.get_instance_ids()
        if not self.quiet:
            print self.instances
        for instance_id in self.instances.keys():
            if not self.quiet:
                print 'Updating instance %s' % (instance_id)
            self.instance_id = instance_id
            self.run_update_dns()

            self.indexes.append(str(self.instance_count))

            self.hostname = None
            self.ip = None
            self.instance_count = None
            self.update_dns = True

    def run_update_dns(self):
        if self.hostname is None:
            self.get_hostname()

        if not self.update_dns:
            if not self.quiet:
                print 'Skipping dns update as server already exists'
            return

        if not self.set_dns_registration:
            if not self.quiet:
                print 'Skipping dns registration as per request'
            return

        if self.ip is None:
            if self.use_public_ip:
                self.current_public_ip()
            else:
                self.current_private_ip()

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
        if not self.quiet:
            print response

    def main(self):
        parser = argparse.ArgumentParser(description='Update route 53 dns based on server tags')
        parser.add_argument('domain', help='Domain name')
        parser.add_argument('--skip-tag-name', action='store_true', default=False, help='Skip setting the tag name')
        parser.add_argument('--skip-dns-registration', action='store_true', default=False, help='If set, only display the dns entry and do run any dns updates')
        parser.add_argument('--quiet', action='store_true', default=False, help='If set, only output the hostname')
        parser.add_argument('--tag-role', default='role', help='Role tag name (default: %(default)s)')
        parser.add_argument('--tag-env', default='env', help='Environment tag name (default: %(default)s)')
        parser.add_argument('--tag-index', default='index', help='Index tag name (default: %(default)s)')
        parser.add_argument('--public-ip', action='store_true', default=False, help='Use public ip instead of private ip')
        parser.add_argument('--name', default=None, help='Ignore tags and just set name')
        parser.add_argument('--role', default=None, help='Ignore tags and use given role')
        parser.add_argument('--env', default=None, help='Ignore tags and use given env')
        parser.add_argument('--instance-id', default=None, help='If given, use instance id given rather than local instance')
        parser.add_argument('--all-tags', action='store_true', default=False, help='If given, run for all instances that match tags for role/env. Can be used with --role and/or --env.')
        args = parser.parse_args()

        self.domain = args.domain
        self.set_tag_name = not args.skip_tag_name
        self.set_dns_registration = not args.skip_dns_registration
        self.quiet = args.quiet
        self.tag_env = args.tag_env
        self.tag_role = args.tag_role
        self.role = args.role
        self.env = args.env
        self.tag_index = args.tag_index
        self.name = args.name
        self.use_public_ip = args.public_ip
        self.instance_id = args.instance_id

        if args.all_tags:
            self.run_update_all()
        else:
            self.run_update_dns()

if __name__ == '__main__':

    launcher = Dns()
    launcher.main()

