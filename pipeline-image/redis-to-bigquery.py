"""This script grabs tweets from a redis server, and stores them in BiqQuery
using the BigQuery Streaming API.
"""

import collections
import json
import os
import time
import urllib

from apiclient import discovery
import dateutil.parser
import httplib2
from oauth2client.client import GoogleCredentials
import redis

# Get info on the Redis host and port from the environment variables.
# The name of this variable comes from the redis service id, 'redismaster'.
REDIS_HOST = os.environ['REDISMASTER_SERVICE_HOST']
REDIS_PORT = os.environ['REDISMASTER_SERVICE_PORT']
REDIS_LIST = os.environ['REDISLIST']

r = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# Get the numeric project ID from the environment variable set in
# the 'bigquery-controller.json' manifest.
PROJECT_ID = os.environ['PROJECT_ID']
BQ_SCOPES = ['https://www.googleapis.com/auth/bigquery']

def create_bigquery_client():
    """Build the bigquery client."""
    credentials = GoogleCredentials.get_application_default()
    if credentials.create_scoped_required():
        credentials = credentials.create_scoped(BQ_SCOPES)
    http = httplib2.Http()
    credentials.authorize(http)
    return discovery.build('bigquery', 'v2', http=http)


def flatten(l):
  """Helper function used to massage the raw tweet data."""
  for el in l:
    if isinstance(el, collections.Iterable) and not isinstance(el, basestring):
      for sub in flatten(el):
        yield sub
    else:
      yield el


def strip_none(data):
  """Do some data massaging."""
  if isinstance(data, dict):
    newdict = {}
    for k,v in data.items():
      if k == 'coordinates' and isinstance(v, list):
        # flatten list
        newdict[k] = list(flatten(v))
      elif k == 'created_at' and v:
        newdict[k] = str(dateutil.parser.parse(v))
      elif v == False:
        newdict[k] = v
      else:
        if k and v:
          newdict[k] = strip_none(v)
    return newdict
  else:
    return data


def write_to_bq(bigquery):
  """Write the data to BigQuery in small chunks."""
  tweets = []
  CHUNK = 50  # The size of the BigQuery insertion batch.
  twstring = ''
  tweet = None
  mtweet = None
  while True:
    while len(tweets) < CHUNK:
      # We'll use a blocking list pop -- it returns when there is new data.
      res = r.brpop(REDIS_LIST)
      twstring = res[1]
      try:
        tweet = json.loads(res[1])
      except Exception, bqe:
        print bqe
      # First do some massaging of the raw data
      mtweet = strip_none(tweet)
      # We only want to write tweets to BigQuery; we'll skip 'delete' and
      # 'limit' information.
      if 'delete' in mtweet:
        continue
      if 'limit' in mtweet:
        print mtweet
        continue
      tweets.append(mtweet)

    try:
      rowlist = []
      # Generate the data that will be sent to BigQuery
      for item in tweets:
        item_row = {"json": item}
        rowlist.append(item_row)
      body = {"rows": rowlist}
      dataset = os.environ['BQ_DATASET']
      table = os.environ['BQ_TABLE']
      # Try the insertion.
      response = bigquery.tabledata().insertAll(
          projectId=PROJECT_ID, datasetId=dataset, tableId=table, body=body
          ).execute()
      print "streaming response: %s" % response
      try:
        # If there was an insertion error returned, print diagnostics.
        if 'insertErrors' in response:
          err_resp = response['insertErrors']
          if 'errors' in err_resp[0] and err_resp[0]['errors']:
            reason = err_resp[0]['errors'][0]['reason']
            if reason == 'timeout' or reason == 'stopped':
              print "error was 'timeout' or 'stopped'."
            else:  # got some other type of error; print for diagnostics
              print twstring
              print '-----------tweet to json string'
              print json.dumps(mtweet)
          else:
            print twstring
            print '-----------tweet to json string'
            print json.dumps(mtweet)
      except Exception, exp:
        print exp
      tweets = []
    except Exception:
      # If an exception was thrown in making the insertion call, try again.
      time.sleep(2)
      print "trying again."
      try:
        response = bigquery.tabledata().insertAll(
            projectId=PROJECT_ID, datasetId=dataset, tableId=table, body=body
            ).execute()
        print "streaming response: %s" % response
      except Exception:
        time.sleep(4)
        print "One more retry."
        try:
          # first refresh on the auth, as if there has been a long gap since we
          # last grabbed data from Redis, we may need to re-auth.
          http = GenerateAuthenticatedHttp(BQ_SCOPE)
          bigquery = build("bigquery", "v2", http=http)
          response = bigquery.tabledata().insertAll(
              projectId=PROJECT_ID, datasetId=dataset, tableId=table, body=body
              ).execute()
          print "streaming response: %s" % response
        except Exception, e3:
          print "Giving up: %s" % e3


if __name__ == '__main__':
  print "starting write to BigQuery...."
  bigquery = create_bigquery_client()
  write_to_bq(bigquery)

