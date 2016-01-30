# tagged-route53
Update route53 dns entries based on ec2 instance tags.

This script will use 3 aws tags and the local ec2 metadata to update route53 dns entries.

Dns format: role-instance_id.environment.domain (e.g www-1.prod.foo.com)

There are 2 read only tags for role and environment and 1 read/write tag for instance_id
as to reuse instance_ids for servers that go down.

Simple usage: tagged-route53.py domain

