#!/bin/bash

# Validate arguments
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <youtube_link> <format_code>"
    exit 1
fi

# Extract and normalize YouTube link
LINK="$1"
CODE="$2"

# Rebuild the full YouTube URL
WATCH_PART=$(echo "$LINK" | grep -o "/watch?.*")
YOUTUBE_URL="https://www.youtube.com$WATCH_PART"

# Set output path
OUTPUT_DIR="/home/sheeye/Videos/Download/youtube"
mkdir -p "$OUTPUT_DIR"

# Format selection
case $CODE in
  0)
    FORMAT='bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    EXT="mp4"
    ;;
  1)
    FORMAT='bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    EXT="mp4"
    ;;
  2)
    FORMAT='bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    EXT="mp4"
    ;;
  3)
    FORMAT='bestaudio'
    EXT="mp3"
    ;;
  4)
    FORMAT='worstaudio'
    EXT="mp3"
    ;;
  5)
    FORMAT='bestaudio'
    EXT="wav"
    ;;
  6)
    FORMAT='worstaudio'
    EXT="wav"
    ;;
  *)
    echo "Invalid format code."
    exit 1
    ;;
esac

# Construct yt-dlp command
if [[ "$EXT" == "mp3" || "$EXT" == "wav" ]]; then
    yt-dlp -x --audio-format "$EXT" -o "$OUTPUT_DIR/%(title)s.%(ext)s" "$YOUTUBE_URL"
else
    yt-dlp -f "$FORMAT" -o "$OUTPUT_DIR/%(title)s.%(ext)s" "$YOUTUBE_URL"
fi
