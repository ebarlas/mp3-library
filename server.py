import json
import random
import urllib.parse
import base64

import boto3

client = boto3.client('dynamodb', region_name='us-west-2')

table = 'mp3s'

VOWELS = 'aeiou'
CONSONANTS = 'bcdfghjklmnpqrstvwxyz'


def generate_word_stem(length):
    return ''.join(random.choice(CONSONANTS if i % 2 == 0 else VOWELS) for i in range(length))


def query_after(collection, field, forward, term, limit):
    params = {
        'TableName': table,
        'IndexName': f'{field}-index',
        'Limit': limit,
        'ScanIndexForward': forward,
        'KeyConditionExpression': f'#collection = :collection and #{field} {">=" if forward else "<="} :{field}',
        'ExpressionAttributeNames': {'#collection': 'collection', f'#{field}': f'term_{field}'},
        'ExpressionAttributeValues': {':collection': {'S': collection}, f':{field}': {'S': term}}
    }
    res = client.query(**params)
    return res['Items']


def random_songs(collection, limit):
    term = generate_word_stem(3)
    forward = random.choice([True, False])
    items = query_after(collection, 'title', forward, term, 200)
    return random.sample(items, min(limit, len(items)))


def query_page(collection, field, value, limit, start_key):
    kce = '#collection = :collection'
    ean = {'#collection': 'collection'}
    eav = {':collection': {'S': collection}}
    params = {
        'TableName': table,
        'IndexName': f'{field}-index',
        'Limit': limit
    }
    if start_key:
        params['ExclusiveStartKey'] = start_key
    if value:
        params |= {
            'KeyConditionExpression': f'{kce} and begins_with(#{field}, :{field})',
            'ExpressionAttributeNames': ean | {f'#{field}': f'term_{field}'},
            'ExpressionAttributeValues': eav | {f':{field}': {'S': value.lower()}}
        }
    else:
        params |= {
            'KeyConditionExpression': kce,
            'ExpressionAttributeNames': ean,
            'ExpressionAttributeValues': eav
        }
    res = client.query(**params)
    return res['Items'], res.get('LastEvaluatedKey')


def convert_item(item):
    d = {
        'collection': item['collection']['S'],
        's3_key': item['s3_key']['S'],
        'filename': item['filename']['S'],
        'filepath': item['filepath']['S']
    }
    for key in ['artist', 'album', 'title']:
        if key in item:
            d[key] = item[key]['S']
    if 'track' in item:
        d['track'] = int(item['track']['N'])
    return d


def convert_items(items):
    return [convert_item(i) for i in items]


def convert_token(token):
    return base64.b64encode(to_json(token).encode('utf-8')).decode('utf-8')


def extract_token(token):
    return json.loads(base64.b64decode(token))


def to_json(val):
    return json.dumps(val, separators=(',', ':'))


def truncate_if_needed(items, token):
    body = {
        'items': convert_items(items)
    }
    if token:
        body['token'] = convert_token(token)
    while len(j := to_json(body)) >= 40_000:
        del body['items'][-1]  # remove trailing item until under 40 KB limit
    return j


def to_response(items, token):
    return {
        'status': '200',
        'statusDescription': 'OK',
        'headers': {
            'content-type': [
                {
                    'key': 'Content-Type',
                    'value': 'application/json'
                }
            ]
        },
        'body': truncate_if_needed(items, token)
    }


def extract_param(request, name):
    if 'querystring' not in request:
        return None

    params = urllib.parse.parse_qs(request['querystring'])
    if name not in params:
        return None

    return params[name][0]


def lambda_handler(event, context):
    request = event['Records'][0]['cf']['request']

    q = '?' + request['querystring'] if 'querystring' in request else ''
    print(f'method={request["method"]}, path={request["uri"]}{q}')

    if request['method'] == 'GET' and '/random' in request['uri']:
        collection = extract_param(request, 'collection')
        plimit = extract_param(request, 'limit')
        limit = int(plimit) if plimit else 100
        if not collection:
            return {'status': '400', 'statusDescription': 'Bad Request'}
        items = random_songs(collection, limit)
        return to_response(items, None)
    if request['method'] == 'GET' and '/songs' in request['uri']:
        collection = extract_param(request, 'collection')
        index = extract_param(request, 'index')
        q = extract_param(request, 'q')
        token = extract_param(request, 'token')
        plimit = extract_param(request, 'limit')
        limit = int(plimit) if plimit else 100
        start_key = extract_token(token) if token else None
        if not collection or not index:
            return {'status': '400', 'statusDescription': 'Bad Request'}
        items, token = query_page(collection, index, q, limit, start_key)
        return to_response(items, token)

    return {
        'status': '404',
        'statusDescription': 'Not Found',
        'body': 'Not Found'
    }
