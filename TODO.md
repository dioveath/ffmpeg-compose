# TODO
- [x] Add ffmpeg progress to task status endpoint
- [x] Add ability to check if there is actually a task with given id
- [x] Add ability to stop task
- [x] Add webhook support on task completion
- [x] Fix Ffmpeg subprocess Error logging (it is not logging the error on status or result)
- [x] Add ability to create reddit post intro video
- [x] Add webhook support for reddit post intro video
- [x] Upload reddit post intro video to minio and return the url in result 
- [x] Optimize and refactor the FFmpegOptions to make it more robust, add options for inputs like -ss, type strict by defining each of ffmpeg options for readability and clarity.
- [x] add GPU support
- [ ] Add ability to concat with files.txt (this is for better optimization)
- [ ] Add default background url to be green screen in reddit_intro endpoint


# Unify all local services??
- [ ] Shift local tts to here with new endpoint.
- [ ] Add ability to upload file to minioserver. Use minio as our file storage
- [ ] Add ability to delete, download file from minioserver