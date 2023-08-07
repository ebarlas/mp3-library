import os
import re
import sys
import time

import boto3
import eyed3

DYNAMO_REGION = 'us-west-2'
DYNAMO_TABLE = 'mp3s'
S3_BUCKET = 'barlasgarden'
S3_REGION = 'us-west-1'
S3_FOLDER = 'mp3s'

DIGIT_ZERO = ord('0')
DIGITS = list(range(DIGIT_ZERO, DIGIT_ZERO + 10, 1))
LETTER_A = ord('a')
LETTERS = list(range(LETTER_A, LETTER_A + 26, 1))


def filter_ascii_printable(s):
    return ''.join(ch for ch in s if 32 <= ord(ch) <= 126)


def make_s3_key(s):
    others = [ord('_'), ord('/')]
    allowed = DIGITS + LETTERS + others
    filtered = ''.join(ch if ord(ch) in allowed else '_' for ch in s.lower())
    collapsed = re.sub(r'_+', '_', filtered)
    return collapsed[0:-4] + '.mp3'


def make_term(s):
    others = [ord(' ')]
    allowed = DIGITS + LETTERS + others
    filtered = ''.join(ch if ord(ch) in allowed else ' ' for ch in s.lower())
    return re.sub(r' +', ' ', filtered)


def merge_terms(ts):
    return '/'.join(t for t in ts if t)


def make_item(audio_file, collection_name, s3_key, file_path, file_name):
    has_tag = hasattr(audio_file, 'tag')
    term_filename = make_term(file_name)
    term_artist = make_term(audio_file.tag.artist) \
        if has_tag and hasattr(audio_file.tag, 'artist') and audio_file.tag.artist \
        else None
    term_album = make_term(audio_file.tag.album) \
        if has_tag and hasattr(audio_file.tag, 'album') and audio_file.tag.album \
        else None
    term_title = make_term(audio_file.tag.title) \
        if has_tag and hasattr(audio_file.tag, 'title') and audio_file.tag.title \
        else None
    track = str(audio_file.tag.track_num[0]) \
        if (has_tag
            and hasattr(audio_file.tag, 'track_num')
            and audio_file.tag.track_num
            and audio_file.tag.track_num[0]) \
        else None
    padded_track = (track if len(track) == 2 else ('0' + track)) if track else None
    terms_artist = merge_terms([term_artist, term_album, padded_track])
    terms_album = merge_terms([term_album, padded_track, term_artist])
    terms_title = merge_terms([term_title, term_artist, term_album])
    item = {
        'collection': {
            'S': collection_name
        },
        's3_key': {
            'S': s3_key
        },
        'filename': {
            'S': file_name
        },
        'filepath': {
            'S': file_path
        },
        'term_filename': {
            'S': term_filename
        }
    }
    if term_artist:
        item |= {'artist': {'S': audio_file.tag.artist}, 'term_artist': {'S': terms_artist}}
    if term_album:
        item |= {'album': {'S': audio_file.tag.album}, 'term_album': {'S': terms_album}}
    if term_title:
        item |= {'title': {'S': audio_file.tag.title}, 'term_title': {'S': terms_title}}
    if track:
        item |= {'track': {'N': track}}
    return item


def put_item(client, item):
    res, put_time = profile(lambda: client.put_item(
        TableName=DYNAMO_TABLE,
        Item=item
    ))
    print(f'  put_item_time={put_time}')
    check_response(res)


def profile(fn):
    t1 = time.monotonic()
    result = fn()
    t2 = time.monotonic()
    return result, t2 - t1


def put_object(client, s3_key, file_path):
    with open(file_path, 'rb') as f:
        content, read_time = profile(lambda: f.read())
        print(f'  read_time={read_time}, content_len={len(content)}')
        res, put_time = profile(lambda: client.put_object(
            Body=content,
            Bucket=S3_BUCKET,
            CacheControl='max-age=31536000, immutable',
            ContentType='audio/mpeg',
            ContentLength=len(content),
            Key=s3_key
        ))
        print(f'  put_object_time={put_time}')
        check_response(res)


def check_response(res):
    if res['ResponseMetadata']['HTTPStatusCode'] != 200:
        print(res)
        sys.exit(1)


def upload(dynamo, s3, collection, root, files, offset):
    for n, (top, f) in enumerate(files):
        rel_top = top.replace(root, '')
        path = f'{top}{f}' if top.endswith('/') else f'{top}/{f}'
        rel_path = f'{rel_top}/{f}' if rel_top else f
        audio_file = eyed3.load(path)
        print(f'[{n + offset}] {path}')
        s3_key = make_s3_key(f'{S3_FOLDER}/{collection}/{rel_path}')
        item = make_item(audio_file, collection, s3_key, rel_top, f)
        put_object(s3, s3_key, path)
        put_item(dynamo, item)


def mp3_files(root):
    return sorted([(top, f) for top, _, files in os.walk(root) for f in files if f.endswith('.mp3')])


def main(collection, root, start, end, dry_run):
    if not root.endswith('/'):
        root += '/'
    files = mp3_files(root)
    print(len(files))
    files = files[start:end]
    for n, f in enumerate(files):
        print(n, f)
    if not dry_run:
        dynamo = boto3.client('dynamodb', region_name=DYNAMO_REGION)
        s3 = boto3.client('s3', region_name=S3_REGION)
        upload(dynamo, s3, collection, root, files, start)


if len(sys.argv) != 6:
    print('required arguments [collection name] [root directory] [inclusive start] [exclusive end] [dry run]')
    sys.exit(1)

main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5].lower() in ('true', 'yes'))
