#!/usr/bin/env bash
export MSYS_NO_PATHCONV=1
F='INFO|WARN|^$|Welcome|JLine|WATCHER|WatchedEvent|Connecting to|Exiting JVM'
run() { echo "\$ $*"; eval "$@" 2>&1 | grep -vE "$F"; echo; }
W2=$(mktemp)

echo "\$ docker exec -it zk2 zkCli.sh -server localhost:2182"
( echo "create -e /ephemeral_demo 'session-owned node'"; sleep 12; echo "quit" ) \
  | docker exec -i zk2 zkCli.sh -server localhost:2182 > "$W2" 2>&1 &
W=$!
sleep 6
echo "[zk: localhost:2182(CONNECTED) 0] create -e /ephemeral_demo 'session-owned node'"
grep -o "Created.*" "$W2"
echo
run docker exec zk1 zkCli.sh -server localhost:2181 ls /
run "docker exec zk1 zkCli.sh -server localhost:2181 stat /ephemeral_demo | grep ephemeralOwner"
wait $W
echo "[zk: localhost:2182(CONNECTED) 1] quit"
echo
run docker exec zk1 zkCli.sh -server localhost:2181 ls /
run docker exec zk1 zkCli.sh -server localhost:2181 get /ephemeral_demo
rm -f "$W2"
