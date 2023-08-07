# MP3 Library

MP3 Library is a web application project that consists of several discrete components.

### Cloud Infrastructure
* S3 Bucket - Store for raw MP3 files
* DynamoDB - Store for MP3 metadata and search terms
* CloudFront - Caches and serves static site content and provide Lambda hosting

### Programs
* `upload.py` - CLI tool that walks directory on local file system and uploads MP3s to S3 and metadata to DynamoDB
* `server.py` - CloudFront Lambda@Edge function for handling metadata HTTP/REST API
* `index.html` - Static site for browsing library, building a playlist, and controlling media player
* `deploy.sh` - Deploy content to S3 and invalidate CloudFront distribution