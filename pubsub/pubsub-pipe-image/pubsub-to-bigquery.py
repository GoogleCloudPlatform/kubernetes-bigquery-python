#!/usr/bin/env python
# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This script grabs tweets from a PubSub topic, and stores them in BiqQuery
using the BigQuery Streaming API.
"""

import base64
import datetime
import json
import os
import time

import utils

# Get the project ID and pubsub topic from the environment variables set in
# the 'bigquery-controller.yaml' manifest.
PROJECT_ID = os.environ['PROJECT_ID']
PUBSUB_TOPIC = os.environ['PUBSUB_TOPIC']
NUM_RETRIES = 3


def fqrn(resource_type, project, resource):
    """Returns a fully qualified resource name for Cloud Pub/Sub."""
    return "projects/{}/{}/{}".format(project, resource_type, resource)


def create_subscription(client, project_name, sub_name):
    """Creates a new subscription to a given topic."""
    print "using pubsub topic: %s" % PUBSUB_TOPIC
    name = get_full_subscription_name(project_name, sub_name)
    body = {'topic': PUBSUB_TOPIC}
    subscription = client.projects().subscriptions().create(
            name=name, body=body).execute(num_retries=NUM_RETRIES)
    print 'Subscription {} was created.'.format(subscription['name'])


def get_full_subscription_name(project, subscription):
    """Returns a fully qualified subscription name."""
    return fqrn('subscriptions', project, subscription)


def pull_messages(client, project_name, sub_name):
    """Pulls messages from a given subscription."""
    BATCH_SIZE = 50
    tweets = []
    subscription = get_full_subscription_name(project_name, sub_name)
    body = {
            'returnImmediately': False,
            'maxMessages': BATCH_SIZE
    }
    try:
        resp = client.projects().subscriptions().pull(
                subscription=subscription, body=body).execute(
                        num_retries=NUM_RETRIES)
    except Exception as e:
        print "Exception: %s" % e
        time.sleep(0.5)
        return
    receivedMessages = resp.get('receivedMessages')
    if receivedMessages is not None:
        ack_ids = []
        for receivedMessage in receivedMessages:
                message = receivedMessage.get('message')
                if message:
                        tweets.append(
                            base64.urlsafe_b64decode(str(message.get('data'))))
                        ack_ids.append(receivedMessage.get('ackId'))
        ack_body = {'ackIds': ack_ids}
        client.projects().subscriptions().acknowledge(
                subscription=subscription, body=ack_body).execute(
                        num_retries=NUM_RETRIES)
    return tweets


def write_to_bq(pubsub, sub_name, bigquery):
    """Write the data to BigQuery in small chunks."""
    tweets = []
    CHUNK = 50  # The size of the BigQuery insertion batch.
    # If no data on the subscription, the time to sleep in seconds
    # before checking again.
    WAIT = 2
    tweet = None
    mtweet = None
    count = 0
    count_max = 50000
    while count < count_max:
        while len(tweets) < CHUNK:
            twmessages = pull_messages(pubsub, PROJECT_ID, sub_name)
            if twmessages:
                for res in twmessages:
                    try:
                        tweet = json.loads(res)
                    except Exception, bqe:
                        print bqe
                    # First do some massaging of the raw data
                    mtweet = utils.cleanup(tweet)
                    # We only want to write tweets to BigQuery; we'll skip
                    # 'delete' and 'limit' information.
                    if 'delete' in mtweet:
                        continue
                    if 'limit' in mtweet:
                        continue
                    tweets.append(mtweet)
            else:
                # pause before checking again
                print 'sleeping...'
                time.sleep(WAIT)
        response = utils.bq_data_insert(bigquery, PROJECT_ID, os.environ['BQ_DATASET'],
                             os.environ['BQ_TABLE'], tweets)
        tweets = []
        count += 1
        if count % 25 == 0:
            print ("processing count: %s of %s at %s: %s" %
                   (count, count_max, datetime.datetime.now(), response))


if __name__ == '__main__':
    topic_info = PUBSUB_TOPIC.split('/')
    topic_name = topic_info[-1]
    sub_name = "tweets-%s" % topic_name
    print "starting write to BigQuery...."
    credentials = utils.get_credentials()
    bigquery = utils.create_bigquery_client(credentials)
    pubsub = utils.create_pubsub_client(credentials)
    try:
        # TODO: check if subscription exists first
        subscription = create_subscription(pubsub, PROJECT_ID, sub_name)
    except Exception, e:
        print e
    write_to_bq(pubsub, sub_name, bigquery)
    print 'exited write loop'
