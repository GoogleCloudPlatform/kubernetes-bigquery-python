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

"""This file contains some utilities used for processing tweet data and writing
data to BigQuery
"""

import collections
import time

from apiclient import discovery
import dateutil.parser
import httplib2
from oauth2client.client import GoogleCredentials

SCOPES = ['https://www.googleapis.com/auth/bigquery',
          'https://www.googleapis.com/auth/pubsub']


def get_credentials():
    """Get the Google credentials needed to access our services."""
    credentials = GoogleCredentials.get_application_default()
    if credentials.create_scoped_required():
            credentials = credentials.create_scoped(SCOPES)
    return credentials


def create_bigquery_client(credentials):
    """Build the bigquery client."""
    http = httplib2.Http()
    credentials.authorize(http)
    return discovery.build('bigquery', 'v2', http=http)


def create_pubsub_client(credentials):
    """Build the pubsub client."""
    http = httplib2.Http()
    credentials.authorize(http)
    return discovery.build('pubsub', 'v1beta2', http=http)


def flatten(l):
    """Helper function used to massage the raw tweet data."""
    for el in l:
        if (isinstance(el, collections.Iterable) and
                not isinstance(el, basestring)):
            for sub in flatten(el):
                yield sub
        else:
            yield el


def cleanup(data):
    """Do some data massaging."""
    if isinstance(data, dict):
        newdict = {}
        for k, v in data.items():
            if (k == 'coordinates') and isinstance(v, list):
                # flatten list
                newdict[k] = list(flatten(v))
            elif k == 'created_at' and v:
                newdict[k] = str(dateutil.parser.parse(v))
            elif v is False:
                newdict[k] = v
            # temporarily, ignore the new 'video_info' info.  The current BQ
            # schema does not support it.
            # TODO: update BigQuery schema
            elif k == 'video_info':
                pass
            else:
                if k and v:
                    newdict[k] = cleanup(v)
        return newdict
    elif isinstance(data, list):
        newlist = []
        for item in data:
            newdata = cleanup(item)
            if newdata:
                newlist.append(newdata)
        return newlist
    else:
        return data


def bq_data_insert(bigquery, project_id, dataset, table, tweets):
    """Insert a list of tweets into the given BigQuery table."""
    WAIT = 2  # retry pause
    try:
        rowlist = []
        # Generate the data that will be sent to BigQuery
        for item in tweets:
            item_row = {"json": item}
            rowlist.append(item_row)
        body = {"rows": rowlist}
        # Try the insertion.
        response = bigquery.tabledata().insertAll(
                projectId=project_id, datasetId=dataset,
                tableId=table, body=body).execute()
        print "streaming response: %s" % response
        # TODO: 'invalid field' errors can be detected here.
    except Exception, e1:
        # If an exception was thrown in making the insertion call, try again.
        print e1
        time.sleep(WAIT)
        print "trying again."
        try:
            response = bigquery.tabledata().insertAll(
                    projectId=project_id, datasetId=dataset,
                    tableId=table, body=body).execute()
            print "streaming response: %s" % response
        except Exception:
            time.sleep(WAIT * 2)
            print "One more retry."
            try:
                # first refresh on the auth, as if there has been a long gap
                # since we last obtained data, we may need to re-auth.
                bigquery = create_bigquery_client()
                response = bigquery.tabledata().insertAll(
                        projectId=project_id, datasetId=dataset,
                        tableId=table, body=body).execute()
                print "streaming response: %s" % response
            except Exception, e3:
                print "Giving up: %s" % e3
