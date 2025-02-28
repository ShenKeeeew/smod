#!/usr/bin/python3
# -*- coding: UTF-8 -*-

import fcntl
import logging
import os
import platform
import socket
import traceback

import importloader
from configloader import get_config, load_config
from server_pool import ServerPool
from shadowsocks import common, shell

switchrule = None
db_instance = None

class WebTransfer(object):
    def __init__(self):
        from multiprocessing import Event

        self.last_update_transfer = {}
        self.event = Event()
        self.port_uid_table = {}
        self.uid_port_table = {}
        self.node_speedlimit = 0.00
        self.traffic_rate = 0.0

        self.detect_text_list = {}

        self.detect_hex_list = {}

        self.mu_only = False

        self.node_ip_list = []
        self.mu_port_list = []

        self.has_stopped = False

    def update_all_user(self, dt_transfer):
        global webapi

        update_transfer = {}

        alive_user_count = 0
        bandwidth_thistime = 0

        data = []
        no_count_id = []
        for id in dt_transfer.keys():
            if dt_transfer[id][0] == 0 and dt_transfer[id][1] == 0:
                continue
            total = dt_transfer[id][0] + dt_transfer[id][1]
            if total < int(get_config().DeviceOnlineMinTraffic) * 1000: # 流量小于 * kb 不上报IP，用于ping测试
                no_count_id.append(self.port_uid_table[id])
            data.append(
                {
                    "u": dt_transfer[id][0],
                    "d": dt_transfer[id][1],
                    "user_id": self.port_uid_table[id],
                }
            )
            update_transfer[id] = dt_transfer[id]
        webapi.postApi(
            "users/traffic", {"node_id": get_config().NODE_ID}, {"data": data}
        )

        webapi.postApi(
            "nodes/%d/info" % (get_config().NODE_ID),
            {"node_id": get_config().NODE_ID},
            {"uptime": str(self.uptime()), "load": str(self.load())},
        )

        online_iplist = ServerPool.get_instance().get_servers_iplist()
        data = []
        for port in online_iplist.keys():
            if self.port_uid_table[port] in no_count_id: # 这些ID在不上报的IDlist中。
                continue
            else:
                for ip in online_iplist[port]:
                    data.append({"ip": ip, "user_id": self.port_uid_table[port]})
        webapi.postApi(
            "users/aliveip", {"node_id": get_config().NODE_ID}, {"data": data}
        )

        detect_log_list = ServerPool.get_instance().get_servers_detect_log()
        data = []
        for port in detect_log_list.keys():
            for rule_id in detect_log_list[port]:
                data.append(
                    {"list_id": rule_id, "user_id": self.port_uid_table[port]}
                )
        webapi.postApi(
            "users/detectlog",
            {"node_id": get_config().NODE_ID},
            {"data": data},
        )

        return update_transfer

    def uptime(self):
        with open("/proc/uptime", "r") as f:
            return float(f.readline().split()[0])

    def load(self):
        import os

        return os.popen(
            'cat /proc/loadavg | awk \'{ print $1" "$2" "$3 }\''
        ).readlines()[0]

    def trafficShow(self, Traffic):
        if Traffic < 1024:
            return str(round((Traffic), 2)) + "B"

        if Traffic < 1024 * 1024:
            return str(round((Traffic / 1024), 2)) + "KB"

        if Traffic < 1024 * 1024 * 1024:
            return str(round((Traffic / 1024 / 1024), 2)) + "MB"

        return str(round((Traffic / 1024 / 1024 / 1024), 2)) + "GB"

    def push_db_all_user(self):
        # 更新用户流量到数据库
        last_transfer = self.last_update_transfer
        curr_transfer = ServerPool.get_instance().get_servers_transfer()
        # 上次和本次的增量
        dt_transfer = {}
        for id in curr_transfer.keys():
            if id in last_transfer:
                if (
                        curr_transfer[id][0]
                        + curr_transfer[id][1]
                        - last_transfer[id][0]
                        - last_transfer[id][1]
                        <= 0
                ):
                    continue
                if (
                        last_transfer[id][0] <= curr_transfer[id][0]
                        and last_transfer[id][1] <= curr_transfer[id][1]
                ):
                    dt_transfer[id] = [
                        curr_transfer[id][0] - last_transfer[id][0],
                        curr_transfer[id][1] - last_transfer[id][1],
                    ]
                else:
                    dt_transfer[id] = [
                        curr_transfer[id][0],
                        curr_transfer[id][1],
                    ]
            else:
                if curr_transfer[id][0] + curr_transfer[id][1] <= 0:
                    continue
                dt_transfer[id] = [curr_transfer[id][0], curr_transfer[id][1]]
        for id in dt_transfer.keys():
            last = last_transfer.get(id, [0, 0])
            last_transfer[id] = [
                last[0] + dt_transfer[id][0],
                last[1] + dt_transfer[id][1],
            ]
        self.last_update_transfer = last_transfer.copy()
        self.update_all_user(dt_transfer)

    def pull_db_all_user(self):
        global webapi

        nodeinfo = webapi.getApi("nodes/%d/info" % (get_config().NODE_ID))

        if not nodeinfo:
            rows = []
            return rows

        self.node_speedlimit = nodeinfo["node_speedlimit"]
        self.traffic_rate = nodeinfo["traffic_rate"]

        self.mu_only = nodeinfo["mu_only"]

        data = webapi.getApi("users", {"node_id": get_config().NODE_ID})

        if not data:
            rows = []
            return rows

        rows = data

        # 读取节点IP
        # SELECT * FROM `ss_node`  where `node_ip` != ''
        self.node_ip_list = []
        data = webapi.getApi("nodes")
        for node in data:
            temp_list = str(node["node_ip"]).split(",")
            self.node_ip_list.append(temp_list[0])

        # 读取审计规则,数据包匹配部分

        self.detect_text_list = {}
        self.detect_hex_list = {}
        data = webapi.getApi("func/detect_rules")
        for rule in data:
            d = {}
            d["id"] = int(rule["id"])
            d["regex"] = str(rule["regex"])
            if int(rule["type"]) == 1:
                self.detect_text_list[d["id"]] = d.copy()
            else:
                self.detect_hex_list[d["id"]] = d.copy()

        return rows

    def cmp(self, val1, val2):
        if isinstance(val1, bytes):
            val1 = common.to_str(val1)
        if isinstance(val2, bytes):
            val2 = common.to_str(val2)
        return val1 == val2

    def del_server_out_of_bound_safe(self, last_rows, rows):
        # 停止超流量的服务
        # 启动没超流量的服务
        # 需要动态载入switchrule，以便实时修改规则

        try:
            switchrule = importloader.load("switchrule")
        except Exception as e:
            logging.error("load switchrule.py fail")
        cur_servers = {}
        new_servers = {}

        md5_users = {}

        self.mu_port_list = []

        for row in rows:
            if row["is_multi_user"] != 0:
                self.mu_port_list.append(int(row["port"]))
                continue

            md5_users[row["id"]] = row.copy()

            md5_users[row["id"]]["md5"] = common.get_md5(
                str(row["id"])
                + row["passwd"]
                + row["method"]
                + row["obfs"]
                + row["protocol"]
            )

        for row in rows:
            self.port_uid_table[row["port"]] = row["id"]
            self.uid_port_table[row["id"]] = row["port"]

        if self.mu_only == 1:
            i = 0
            while i < len(rows):
                if rows[i]["is_multi_user"] == 0:
                    rows.pop(i)
                    i -= 1
                else:
                    pass
                i += 1

        if self.mu_only == -1:
            i = 0
            while i < len(rows):
                if rows[i]["is_multi_user"] != 0:
                    rows.pop(i)
                    i -= 1
                else:
                    pass
                i += 1

        for row in rows:
            port = row["port"]
            user_id = row["id"]
            passwd = common.to_bytes(row["passwd"])
            cfg = {"password": passwd}

            read_config_keys = [
                "method",
                "obfs",
                "obfs_param",
                "protocol",
                "protocol_param",
                "forbidden_ip",
                "forbidden_port",
                "node_speedlimit",
                "is_multi_user",
            ]

            for name in read_config_keys:
                if name in row and row[name]:
                    cfg[name] = row[name]

            merge_config_keys = ["password"] + read_config_keys
            for name in cfg.keys():
                if hasattr(cfg[name], "encode"):
                    try:
                        cfg[name] = cfg[name].encode("utf-8")
                    except Exception as e:
                        logging.warning(
                            'encode cfg key "%s" fail, val "%s"'
                            % (name, cfg[name])
                        )

            if "node_speedlimit" in cfg:
                if (
                        float(self.node_speedlimit) > 0.0
                        or float(cfg["node_speedlimit"]) > 0.0
                ):
                    cfg["node_speedlimit"] = max(
                        float(self.node_speedlimit),
                        float(cfg["node_speedlimit"]),
                    )
            else:
                cfg["node_speedlimit"] = max(
                    float(self.node_speedlimit), float(0.00)
                )

            if "forbidden_ip" not in cfg:
                cfg["forbidden_ip"] = ""

            if "forbidden_port" not in cfg:
                cfg["forbidden_port"] = ""

            if "protocol_param" not in cfg:
                cfg["protocol_param"] = ""

            if "obfs_param" not in cfg:
                cfg["obfs_param"] = ""

            if "is_multi_user" not in cfg:
                cfg["is_multi_user"] = 0

            if port not in cur_servers:
                cur_servers[port] = passwd
            else:
                logging.error(
                    "more than one user use the same port [%s]" % (port,)
                )
                continue

            if cfg["is_multi_user"] != 0:
                cfg["users_table"] = md5_users.copy()

            cfg["detect_hex_list"] = self.detect_hex_list.copy()
            cfg["detect_text_list"] = self.detect_text_list.copy()

            if ServerPool.get_instance().server_is_run(port) > 0:
                cfgchange = False

                if port in ServerPool.get_instance().tcp_servers_pool:
                    ServerPool.get_instance().tcp_servers_pool[
                        port
                    ].modify_detect_text_list(self.detect_text_list)
                    ServerPool.get_instance().tcp_servers_pool[
                        port
                    ].modify_detect_hex_list(self.detect_hex_list)
                if port in ServerPool.get_instance().tcp_ipv6_servers_pool:
                    ServerPool.get_instance().tcp_ipv6_servers_pool[
                        port
                    ].modify_detect_text_list(self.detect_text_list)
                    ServerPool.get_instance().tcp_ipv6_servers_pool[
                        port
                    ].modify_detect_hex_list(self.detect_hex_list)
                if port in ServerPool.get_instance().udp_servers_pool:
                    ServerPool.get_instance().udp_servers_pool[
                        port
                    ].modify_detect_text_list(self.detect_text_list)
                    ServerPool.get_instance().udp_servers_pool[
                        port
                    ].modify_detect_hex_list(self.detect_hex_list)
                if port in ServerPool.get_instance().udp_ipv6_servers_pool:
                    ServerPool.get_instance().udp_ipv6_servers_pool[
                        port
                    ].modify_detect_text_list(self.detect_text_list)
                    ServerPool.get_instance().udp_ipv6_servers_pool[
                        port
                    ].modify_detect_hex_list(self.detect_hex_list)

                if row["is_multi_user"] != 0:
                    if port in ServerPool.get_instance().tcp_servers_pool:
                        ServerPool.get_instance().tcp_servers_pool[
                            port
                        ].modify_multi_user_table(md5_users)
                    if port in ServerPool.get_instance().tcp_ipv6_servers_pool:
                        ServerPool.get_instance().tcp_ipv6_servers_pool[
                            port
                        ].modify_multi_user_table(md5_users)
                    if port in ServerPool.get_instance().udp_servers_pool:
                        ServerPool.get_instance().udp_servers_pool[
                            port
                        ].modify_multi_user_table(md5_users)
                    if port in ServerPool.get_instance().udp_ipv6_servers_pool:
                        ServerPool.get_instance().udp_ipv6_servers_pool[
                            port
                        ].modify_multi_user_table(md5_users)

                if port in ServerPool.get_instance().tcp_servers_pool:
                    relay = ServerPool.get_instance().tcp_servers_pool[port]
                    for name in merge_config_keys:
                        if name in cfg and not self.cmp(
                                cfg[name], relay._config[name]
                        ):
                            cfgchange = True
                            break
                if (
                        not cfgchange
                        and port in ServerPool.get_instance().tcp_ipv6_servers_pool
                ):
                    relay = ServerPool.get_instance().tcp_ipv6_servers_pool[
                        port
                    ]
                    for name in merge_config_keys:
                        if name in cfg and not self.cmp(
                                cfg[name], relay._config[name]
                        ):
                            cfgchange = True
                            break
                # config changed
                if cfgchange:
                    self.del_server(port, "config changed")
                    new_servers[port] = (passwd, cfg)
            elif ServerPool.get_instance().server_run_status(port) is False:
                # new_servers[port] = passwd
                self.new_server(port, passwd, cfg)

        for row in last_rows:
            if row["port"] in cur_servers:
                pass
            else:
                self.del_server(row["port"], "port not exist")

        if len(new_servers) > 0:
            from shadowsocks import eventloop

            self.event.wait(
                eventloop.TIMEOUT_PRECISION + eventloop.TIMEOUT_PRECISION / 2
            )
            for port in new_servers.keys():
                passwd, cfg = new_servers[port]
                self.new_server(port, passwd, cfg)

        ServerPool.get_instance().push_uid_port_table(self.uid_port_table)

    def del_server(self, port, reason):
        logging.info(
            "db stop server at port [%s] reason: %s!" % (port, reason)
        )
        ServerPool.get_instance().cb_del_server(port)
        if port in self.last_update_transfer:
            del self.last_update_transfer[port]

        for mu_user_port in self.mu_port_list:
            if mu_user_port in ServerPool.get_instance().tcp_servers_pool:
                ServerPool.get_instance().tcp_servers_pool[
                    mu_user_port
                ].reset_single_multi_user_traffic(self.port_uid_table[port])
            if mu_user_port in ServerPool.get_instance().tcp_ipv6_servers_pool:
                ServerPool.get_instance().tcp_ipv6_servers_pool[
                    mu_user_port
                ].reset_single_multi_user_traffic(self.port_uid_table[port])
            if mu_user_port in ServerPool.get_instance().udp_servers_pool:
                ServerPool.get_instance().udp_servers_pool[
                    mu_user_port
                ].reset_single_multi_user_traffic(self.port_uid_table[port])
            if mu_user_port in ServerPool.get_instance().udp_ipv6_servers_pool:
                ServerPool.get_instance().udp_ipv6_servers_pool[
                    mu_user_port
                ].reset_single_multi_user_traffic(self.port_uid_table[port])

    def new_server(self, port, passwd, cfg):
        protocol = cfg.get(
            "protocol",
            ServerPool.get_instance().config.get("protocol", "origin"),
        )
        method = cfg.get(
            "method", ServerPool.get_instance().config.get("method", "None")
        )
        obfs = cfg.get(
            "obfs", ServerPool.get_instance().config.get("obfs", "plain")
        )
        logging.info(
            "db start server at port [%s] pass [%s] protocol [%s] method [%s] obfs [%s]"
            % (port, passwd, protocol, method, obfs)
        )
        ServerPool.get_instance().new_server(port, cfg)

    @staticmethod
    def del_servers():
        global db_instance
        for port in [
            v for v in ServerPool.get_instance().tcp_servers_pool.keys()
        ]:
            if ServerPool.get_instance().server_is_run(port) > 0:
                ServerPool.get_instance().cb_del_server(port)
                if port in db_instance.last_update_transfer:
                    del db_instance.last_update_transfer[port]
        for port in [
            v for v in ServerPool.get_instance().tcp_ipv6_servers_pool.keys()
        ]:
            if ServerPool.get_instance().server_is_run(port) > 0:
                ServerPool.get_instance().cb_del_server(port)
                if port in db_instance.last_update_transfer:
                    del db_instance.last_update_transfer[port]

    @staticmethod
    def thread_db(obj):
        import socket
        import webapi_utils

        global db_instance
        global webapi
        timeout = 60
        socket.setdefaulttimeout(timeout)
        last_rows = []
        db_instance = obj()
        webapi = webapi_utils.WebApi()

        shell.log_shadowsocks_version()
        try:
            import resource

            logging.info(
                "current process RLIMIT_NOFILE resource: soft %d hard %d"
                % resource.getrlimit(resource.RLIMIT_NOFILE)
            )
        except:
            pass
        try:
            while True:
                load_config()
                try:
                    ping = webapi.getApi("func/ping")
                    if ping is None:
                        logging.error(
                            "something wrong with your http api, please check your config and website status and try again later."
                        )
                    else:
                        db_instance.push_db_all_user()
                        rows = db_instance.pull_db_all_user()
                        db_instance.del_server_out_of_bound_safe(
                            last_rows, rows
                        )
                        last_rows = rows
                except Exception as e:
                    trace = traceback.format_exc()
                    logging.error(trace)
                    # logging.warn('db thread except:%s' % e)
                if (
                        db_instance.event.wait(60)
                        or not db_instance.is_all_thread_alive()
                ):
                    break
                if db_instance.has_stopped:
                    break
        except KeyboardInterrupt as e:
            pass
        db_instance.del_servers()
        ServerPool.get_instance().stop()
        db_instance = None

    @staticmethod
    def thread_db_stop():
        global db_instance
        db_instance.has_stopped = True
        db_instance.event.set()

    def is_all_thread_alive(self):
        if not ServerPool.get_instance().thread.is_alive():
            return False
        return True
