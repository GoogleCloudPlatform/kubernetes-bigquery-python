FROM google/python

RUN pip install --upgrade pip
RUN pip install tweepy
RUN pip install --upgrade google-api-python-client
RUN pip install redis
RUN pip install python-dateutil

ADD twitter-to-redis.py /twitter-to-redis.py
ADD redis-to-bigquery.py /redis-to-bigquery.py
ADD controller.py /controller.py
ADD utils.py /utils.py

CMD python controller.py
