#!/usr/bin/env bash
export MSYS_NO_PATHCONV=1
run() { echo "\$ $*"; eval "$@" 2>&1 | grep -vE 'INFO|WARN|^$|Welcome|JLine|WATCHER|WatchedEvent|ZooKeeper JMX|Using config|Client port found|Connecting to|Exiting JVM'; echo; }
st() { for s in zk1 zk2 zk3; do run docker exec $s zkServer.sh status; done; }
port() { docker exec $1 grep clientPort /conf/zoo.cfg | cut -d= -f2 | tr -d '\r'; }

docker exec zk1 zkCli.sh -server localhost:2181 delete /test_one_down >/dev/null 2>&1
st
L=$(for s in zk1 zk2 zk3; do docker exec $s zkServer.sh status 2>&1 | grep -q leader && echo $s; done)
F=($(echo zk1 zk2 zk3 | tr ' ' '\n' | grep -v $L))
F1=${F[0]}; F2=${F[1]}

run docker stop $L
sleep 5
st
run docker exec $F1 zkCli.sh -server localhost:$(port $F1) create /test_one_down hello
run docker exec $F1 zkCli.sh -server localhost:$(port $F1) get /test_one_down

run docker stop $F1
sleep 5
st
run "timeout 25 docker exec $F2 zkCli.sh -server localhost:$(port $F2) ls / | grep KeeperErrorCode"
run "docker exec $F2 bash -c 'echo srvr | nc -w 2 localhost $(port $F2)'"

run docker start $L $F1
sleep 25
st
run docker exec zk1 zkCli.sh -server localhost:2181 get /test_one_down
