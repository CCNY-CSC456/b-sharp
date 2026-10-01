#!/bin/bash
# test-messaging.sh — proves the whole thing works end to end.
# Start the server first (in another terminal, from repo root):
#   uvicorn src.tower.messaging.main:app --reload
# Then run:  bash scripts/test-messaging.sh

# Where the server is listening
URL="localhost:8000/messages"

# Helper to send one message.  Usage:  send <sender> <recipient> "<content>"
# -s        = silent (hides curl's progress bar)
# -X POST   = this is a send, not a read
# -H ...    = tells the server the body is JSON
# -d ...    = the JSON body itself; $1 $2 $3 are the 3 arguments passed in
send() {
  curl -s -X POST $URL -H "Content-Type: application/json" \
    -d "{\"sender\":\"$1\",\"recipient\":\"$2\",\"content\":\"$3\"}"
  echo  # newline so output stays readable
}

# Step 1: send messages between the subsystems.
# Each should print {"status":"sent"}
echo "--- sending ---"
send radar   tower   "AA123 at 5000ft hdg 270"
send tower   command "requesting runway change for AA123"
send command tower   "runway change approved"
send command radar   "track AA123 closely"

# Step 2: check every subsystem's inbox.
# Each should only show the messages addressed to it.
# (curl with no -X does a GET by default)
echo "--- inboxes ---"
for r in radar tower command; do
  echo "$r:"; curl -s "$URL?recipient=$r"; echo
done
