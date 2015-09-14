#!/usr/bin/env python
# Copyright 2014 Google Inc. All Rights Reserved.
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

"""This script uses the Twitter Streaming API, via the tweepy library,
to pull in tweets and store them in a Redis server.
"""

import datetime
import os

import redis
from tweepy import OAuthHandler
from tweepy import Stream
from tweepy.streaming import StreamListener

# Get your twitter credentials from the environment variables.
# These are set in the 'twitter-stream.json' manifest file.
consumer_key = os.environ['CONSUMERKEY']
consumer_secret = os.environ['CONSUMERSECRET']
access_token = os.environ['ACCESSTOKEN']
access_token_secret = os.environ['ACCESSTOKENSEC']

# Get info on the Redis host and port from the environment variables.
# The name of this variable comes from the redis service id, 'redismaster'.
REDIS_HOST = os.environ['REDISMASTER_SERVICE_HOST']
REDIS_PORT = os.environ['REDISMASTER_SERVICE_PORT']
REDIS_LIST = os.environ['REDISLIST']


class StdOutListener(StreamListener):
    """A listener handles tweets that are received from the stream.
    This listener dumps the tweets into Redis.
    """

    count = 0
    redis_errors = 0
    allowed_redis_errors = 3
    twstring = ''
    tweets = []
    r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0)
    total_tweets = 10000000

    def write_to_redis(self, tw):
        try:
            self.r.lpush(REDIS_LIST, tw)
        except:
            print 'Problem adding data to Redis.'
            self.redis_errors += 1

    def on_data(self, data):
        """What to do when tweet data is received."""
        self.write_to_redis(data)
        self.count += 1
        # if we've grabbed more than total_tweets tweets, exit the script.
        # If this script is being run in the context of a kubernetes
        # replicationController, the pod will be restarted fresh when
        # that happens.
        if self.count > self.total_tweets:
            return False
        if self.redis_errors > self.allowed_redis_errors:
            print 'too many redis errors.'
            return False
        if (self.count % 1000) == 0:
            print 'count is: %s at %s' % (self.count, datetime.datetime.now())
        return True

    def on_error(self, status):
        print status


if __name__ == '__main__':
    print '....'
    listener = StdOutListener()
    auth = OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    print 'stream mode is: %s' % os.environ['TWSTREAMMODE']

    stream = Stream(auth, listener)
    # set up the streaming depending upon whether our mode is 'sample', which
    # will sample the twitter public stream. If not 'sample', instead track
    # the given set of keywords.
    # This environment var is set in the 'twitter-stream.yaml' file.
    if os.environ['TWSTREAMMODE'] == 'sample':
        stream.sample()
    else:
        stream.filter(
                track=['bigdata', 'kubernetes', 'bigquery', 'docker', 'google',
                       'googlecloud', 'golang', 'dataflow',
                       'containers', 'appengine', 'gcp', 'compute',
                       'scalability', 'gigaom', 'news', 'tech', 'apple',
                       'amazon', 'cluster', 'distributed', 'computing',
                       'cloud', 'android', 'mobile', 'ios', 'iphone',
                       'python', 'recode', 'techcrunch', 'timoreilly']
                )
