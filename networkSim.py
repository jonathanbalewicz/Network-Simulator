"""
Simulates networks of random networks with random traffic. Stores data that can be decoded with dataDecoder.py.
After measuring the ping latency from a central node to all nodes of a specified number of window within a window of specified length of time, a random link is cut. Then the ping latency is found for all nodes from a central node for a specified number of windows before the program finishes.
Data includes the average ping latency from a central node recorded over a set number of windows.
Run controller(s) at CONTROLLER_IPS port 6633.

Written by ECE capstone 2020-21 G20 at the University of Manitoba.

"""


from mininet.net import Mininet
import thread as th2
import threading
from mininet.node import Ryu
from mininet.node import RemoteController
import random
import csv
import copy
import os
import time

from mininet.link import TCLink

SIMULATIONS_PER_FILE = 1
FILES = 1
FILE_START_NUMBER = 1
THREAD_COUNT = 8
CONTROLLER_IPS = ["192.168.56.102", "192.168.57.102"]

MAX_LOOP_SIZE = 15  # 100
MAX_BRANCH_SIZE = 15
MIN_NODE = 10  # but the actual limitation should be MIN_NODE + MAX_LOOP_SIZE = 25
MAX_NODE = 75

TIME_BETWEEN_PINGS = 30  # s
PINGS_PER_WINDOW = 4
WINDOW_COUNT = 5
LINK_CUT_WINDOW = 2
MAX_TRAFFIC_DURATION = 5
MAX_LINK_DELAY = 5  # ms
MAX_LINK_LOSS = 1
TRAFFIC_LEVEL = 0.05
CHANCE_OF_NO_LINK_CUT = 0.2

Host_ID = 0
Switch_ID = 0
Host_To_Adj_Index = []
Switch_To_Adj_Index = []
INDEX_LOCK = threading.Lock()

###
### Repeatedly ping from the central_node_input to other_node in network when the pingLock is acquired according to the WINDOW_COUNT, PINGS_PER_WINDOW,
### and TIME_BETWEEN_PINGS.
### Returns a list of lists of average latencies of each window for each node.
###
class NodePinger(threading.Thread):
    def __init__(self, central_node_input, other_node, network, pingLock):
        threading.Thread.__init__(self)
        self.central_node_input = central_node_input
        self.other_node = other_node
        self.network = network
        self.latency_list_o = []
        self.pingLock = pingLock

    def run(self):
        for i in range(WINDOW_COUNT):
            for k in range(PINGS_PER_WINDOW):
                start = time.time()
                latency_list_i = []
                self.pingLock.acquire()
                if self.central_node_input.waiting or not self.central_node_input.shell:
                    time.sleep(1.0)
                if self.other_node.waiting or not self.other_node.shell:
                    time.sleep(1.0)
                if not (self.central_node_input.waiting or self.other_node.waiting) or not self.central_node_input.shell or not self.other_node.shell:
                    ping_delays = self.network.pingFull(hosts=[self.central_node_input, self.other_node], timeout='1')
                    test_outputs = ping_delays[0]
                    node, dest, ping_outputs = test_outputs
                    sent, received, rttmin, rttavg, rttmax, rttdev = ping_outputs
                    if rttavg > 0.0:
                        latency_list_i.append(rttavg)
                    elif k == 0:
                        latency_list_i.append(0.0)
                self.pingLock.release()
                if TIME_BETWEEN_PINGS - (time.time() - start) > 0:
                    time.sleep(TIME_BETWEEN_PINGS - (time.time() - start))
            self.latency_list_o.append(sum(latency_list_i) / PINGS_PER_WINDOW)


class Simulator(threading.Thread):
    def __init__(self, threadID):
        threading.Thread.__init__(self)
        self.switchList = []
        self.selectList = []
        self.net = Mininet(link=TCLink)
        self.switch_number = 0
        self.adj_matrix = []
        self.threadID = threadID
        self.pingLock = threading.Lock()
        self.linkList = []
        self.adj_matrix_new = []

    # deleteLink( theNodes )
    #
    # Purpose:   Retrieve the name of the node, then delete the node.
    #
    def deleteLink(self, theNodes):
        # Assign names
        n1 = theNodes[0].name
        name1 = n1.split("-")
        n2 = theNodes[1].name
        name2 = n2.split("-")
        print("\n Deleted Link: ")
        print(name1[0])
        print(name2[0])
        num1 = Switch_To_Adj_Index[int(name1[0].split("s")[1])]
        num2 = Switch_To_Adj_Index[int(name2[0].split("s")[1])]
        assert (self.adj_matrix_new[num1][num2] == 1)
        self.adj_matrix_new[num1][num2] = 0
        self.adj_matrix_new[num2][num1] = 0
        self.net.configLinkStatus(name1[0], name2[0], 'down')

    # selectCentralNode()
    #
    # Purpose: Given a list of nodes, randomly select a node as the central
    # node (or reference node).
    #
    def selectCentralNode(self, network_nodes):
        reference_node_index = random.randrange(len(network_nodes))
        reference_node = network_nodes[reference_node_index]
        return reference_node, reference_node_index

    # detectLinkFaults()
    #
    # Purpose: Ping connections between a central node and other nodes in the
    # network; output the nodes that the central node could not connect to.
    #
    def detectLinkFaults(self, network, list_of_nodes, central_node_index):
        assert (len(list_of_nodes) > 0)

        disconnected_nodes = []
        central_node = list_of_nodes[central_node_index]

        for i in range(0, len(list_of_nodes)):
            if i != central_node_index:
                packet_loss = int(network.ping(hosts=[central_node, list_of_nodes[i]], timeout='5'))
                if packet_loss == 100:
                    packet_loss = int(network.ping(hosts=[central_node, list_of_nodes[i]], timeout='5'))
                    if packet_loss == 100:
                        disconnected_nodes.append(1)
                    else:
                        disconnected_nodes.append(0)
                else:
                    disconnected_nodes.append(0)
            else:
                disconnected_nodes.append(0)

        return disconnected_nodes

    # detectLinkFaults()
    #
    # Purpose: Ping connections between a central node and other nodes in the
    # network; output the nodes that the central node could not connect to.
    #
    def findPingLatenciesAndCutLink(self, network, list_of_nodes, central_node_index, link_cut):
        assert (len(list_of_nodes) > 0)

        latencyListI = []
        central_node_i = list_of_nodes[central_node_index]
        nodePingerThreads = []

        # initialize threads
        j = 0
        for node in list_of_nodes:
            if j != central_node_index:
                nodePingerThreads.append(NodePinger(central_node_i, node, network, self.pingLock))
            j += 1
        for t in nodePingerThreads:
            t.start()

        # wait, then cut the link
        if link_cut is not None:
            for i in range(WINDOW_COUNT):
                if i == LINK_CUT_WINDOW:
                    self.deleteLink(link_cut)
                    break
                time.sleep(TIME_BETWEEN_PINGS * PINGS_PER_WINDOW)

        # gather data from the threads
        for t in nodePingerThreads:
            t.join()
        for i in range(WINDOW_COUNT):
            k = 0
            for j in range(0, len(list_of_nodes)):
                if int(j) == int(central_node_index):
                    latencyListI.append(0)
                    k -= 1
                else:
                    latencyListI.append(nodePingerThreads[k].latency_list_o[i])
                k += 1
        return latencyListI

    # printData
    #
    # Purpose: Print the entries of a list.
    #
    def printData(self, data):
        assert (len(data) > 0)
        for i in range(0, len(data)):
            print(data[i])

    def addBranches(self, net_i, switch, sn, connected_switch, sn_before):
        global Switch_ID
        r = random.randint(1, MAX_BRANCH_SIZE) // (self.switch_number - sn_before + 1)
        if (r > 0) and (connected_switch is not None):
            self.linkList.append([switch, connected_switch])
        for _ in range(r):
            self.switch_number += 1
            INDEX_LOCK.acquire()
            Switch_To_Adj_Index.append(self.switch_number)
            sw2 = net_i.addSwitch('s' + str(Switch_ID), protocols="OpenFlow13")
            Switch_ID += 1
            INDEX_LOCK.release()
            self.switchList.append(sw2)
            print("add link ")
            print(switch)
            print(sw2)
            self.addRandomLink(net_i, switch, sw2)
            """adj_matrix.append([])
            for i in range(len(adj_matrix) - 1):
                if i != sn:
                    adj_matrix[switch_number].append(0)
                    adj_matrix[i].append(0)
                else:
                    adj_matrix[i].append(1)
                    adj_matrix[switch_number].append(1)
    
            adj_matrix[switch_number].append(0)"""
            self.addBranches(net_i, sw2, self.switch_number, switch, sn_before)

    # addLoops
    #
    # create random loop of random size
    def addLoops(self, sw, sn):
        global Switch_ID
        ln = random.randint(3, MAX_LOOP_SIZE)  # number of nodes in loops
        ln_array = []
        INDEX_LOCK.acquire()
        for i in range(1, ln + 1):
            Switch_To_Adj_Index.append(sn + i)
            self.switchList.append(self.net.addSwitch('s' + str(Switch_ID), protocols="OpenFlow13"))
            if i != 0: ln_array.append(sn + i)
            Switch_ID += 1
        INDEX_LOCK.release()
        random.shuffle(ln_array)
        ln_array.insert(0, sn)
        for i in range(ln + 1):
            if i == ln:  # connect last and first switch
                self.addRandomLink(self.net, self.switchList[ln_array[i]], self.switchList[ln_array[0]])
                self.selectList.append([self.switchList[ln_array[i]], self.switchList[ln_array[0]]])
            else:
                self.addRandomLink(self.net, self.switchList[ln_array[i]], self.switchList[ln_array[i + 1]])
                self.selectList.append([self.switchList[ln_array[i]], self.switchList[ln_array[i + 1]]])
        self.switch_number += ln
        sn += ln

    # addRandomNetwork
    #
    # put random number of loops and branches together in random location
    def addRandomNetwork(self, netI, switch, sn):  # put loops and branches together
        self.total_size = random.randint(MIN_NODE + MAX_LOOP_SIZE, MAX_NODE)
        while self.switch_number in range(self.total_size - MAX_LOOP_SIZE):
            next_network = random.randint(0, 1)
            if next_network == 1 or self.switch_number < 4:
                self.addBranches(netI, self.switchList[self.switch_number], self.switch_number, None,
                                 self.switch_number)
            elif next_network == 0:
                self.addLoops(self.switchList[self.switch_number], self.switch_number)

    def createMatrix(self, switchList, linkList):
        self.adj_matrix = [[0] * (len(switchList)) for index in range(len(switchList))]
        for i in range(len(linkList)):
            sw1 = Switch_To_Adj_Index[int(linkList[i][0].name.split("-")[0].split("s")[1])]
            # print sw1
            sw2 = Switch_To_Adj_Index[int(linkList[i][1].name.split("-")[0].split("s")[1])]
            # print sw2
            self.adj_matrix[int(sw1)][int(sw2)] = 1
            self.adj_matrix[int(sw2)][int(sw1)] = 1

    def addRandomLink(self, net_i, node1, node2):
        bw_i = random.randint(1, 1000)
        linkopts = dict(bw=bw_i,
                        delay=str(random.randint(1, MAX_LINK_DELAY)) + 'ms',
                        loss=random.randint(0, MAX_LINK_LOSS),
                        max_queue_size=random.randint(100, 10000) + bw_i,
                        use_htb=random.choice([True, False]))
        net_i.addLink(node1, node2, **linkopts)

###
### Generate random Iperf traffic in network for duration seconds at traffic_level.
###
    def generateRandomTraffic(self, network, duration, traffic_level):
        print("Traffic being generated for:"+str(duration)+" s")
        start = time.time()
        network_size = len(network.hosts)
        port = 5001
        wait_time = (1.0 / (traffic_level * network_size))
        while time.time() - start < duration:
            loop_start = time.time()
            port += 1
            self.generateIperfTraffic(network.hosts[random.randint(0, network_size - 1)],
                                      network.hosts[random.randint(0, network_size - 1)],
                                      random.randint(1, MAX_TRAFFIC_DURATION),
                                      port)

            if wait_time - (time.time() - loop_start) > 0:
                time.sleep(wait_time - (time.time() - loop_start))
            else:
                print("TRAFFIC DELAYED " + str(wait_time - (time.time() - loop_start)))

    def generateIperfTraffic(self, src, dst, duration, port_i):
        protocol = "TCP"
        port_argument = str(port_i)

        # create cmd
        server_cmd = "iperf -s "
        server_cmd += " -p "
        server_cmd += port_argument
        server_cmd += " -i "
        server_cmd += str(2)
        #server_cmd += " >> "
        #server_cmd += "/home/mininet/mininet/custom/flow.txt"
        server_cmd += " & "

        client_cmd = "iperf -c "
        client_cmd += dst.IP() + " "
        client_cmd += " -p "
        client_cmd += port_argument
        client_cmd += " -t "
        client_cmd += str(duration)
        client_cmd += " & "

        # send the cmd
        print(server_cmd)
        if dst.waiting or not dst.shell:
            time.sleep(1)
        if src.waiting or not src.shell:
            time.sleep(1)
        if dst.waiting or src.waiting or not dst.shell or not src.shell:
            print("TRAFFIC CANCELLED")
            return
        dst.cmdPrint(server_cmd)
        src.cmdPrint(client_cmd)

    def run(self):
        # tree_topo = TreeTopo(depth=2,fanout=3)
        # net = Mininet(topo=tree_topo, cleanup=True)
        global Host_ID
        global Switch_ID
        for d in range(FILES):
            lines = [[]]
            simulations_per_file = SIMULATIONS_PER_FILE
            for s in range(SIMULATIONS_PER_FILE):

                self.switchList = []
                self.selectList = []
                self.net = Mininet(link=TCLink)
                self.switch_number = 0
                self.adj_matrix = []
                self.adj_matrix_new = []
                self.linkList = []

                print("Starting Simulation: " + str(s) + " for file " + str(d))

                c0 = self.net.addController(controller=RemoteController,
                                            ip=CONTROLLER_IPS[self.threadID % len(CONTROLLER_IPS)],
                                            port=6633)

                INDEX_LOCK.acquire()
                Switch_To_Adj_Index.append(0)
                sw = self.net.addSwitch('s' + str(Switch_ID), protocols="OpenFlow13")
                Switch_ID += 1
                INDEX_LOCK.release()

                self.switchList.append(sw)
                self.addRandomNetwork(self.net, sw, self.switch_number)
                self.linkList = self.linkList + self.selectList
                self.createMatrix(self.switchList, self.linkList)

                self.adj_matrix_new = copy.deepcopy(self.adj_matrix)

                if self.switch_number < 4 or len(self.selectList) < 4:
                    simulations_per_file -= 1
                    continue
                switches = self.net.switches
                links = self.net.links[:]
                h = 0
                INDEX_LOCK.acquire()
                for switch in switches:
                    Host_To_Adj_Index.append(h)
                    host = self.net.addHost('hs' + str(Host_ID))
                    self.net.addLink(host, switch)
                    Host_ID += 1
                    h += 1
                INDEX_LOCK.release()
                self.net.build()
                c0.start()
                for switch in switches:
                    switch.start([c0])

                central_node, central_node_index = self.selectCentralNode(self.net.hosts)
                time.sleep(180 + (self.threadID * 2))
                # generateIperfTraffic(net.hosts[0], net.hosts[1], 500)

                th2.start_new_thread(self.generateRandomTraffic,
                                     (
                                         self.net, WINDOW_COUNT * PINGS_PER_WINDOW * TIME_BETWEEN_PINGS,
                                         TRAFFIC_LEVEL,))
                if random.random() < CHANCE_OF_NO_LINK_CUT:
                    link_to_cut = None
                else:
                    link_to_cut = self.selectList[random.randrange(len(self.selectList))]
                latency_list = self.findPingLatenciesAndCutLink(self.net, self.net.hosts, central_node_index,
                                                                link_to_cut)
                disconnected_nodes = self.detectLinkFaults(self.net, self.net.hosts, central_node_index)
                print("\nThe central node was unable to connect to the following node(s):")
                print(disconnected_nodes)

                self.net.stop()

                line = [self.switch_number + 1, central_node_index]
                line = line + disconnected_nodes
                line = line + latency_list
                flat_adj = []
                for sub in self.adj_matrix:
                    for item in sub:
                        flat_adj.append(item)
                for sub in self.adj_matrix_new:
                    for item in sub:
                        flat_adj.append(item)
                line = line + flat_adj

                lines.append(line)
            lines[0] = [simulations_per_file,
                      TIME_BETWEEN_PINGS,
                      PINGS_PER_WINDOW,
                      WINDOW_COUNT,
                      LINK_CUT_WINDOW,
                      MAX_TRAFFIC_DURATION]
            file_name = "dataWLatency" + str(d + FILE_START_NUMBER) + "t" + str(self.threadID) + ".csv"
            with open(file_name, 'w') as f:
                writer = csv.writer(f)
                writer.writerows(lines)
            print("wrote to " + file_name)


simulatorThreads = []
for threadID in range(THREAD_COUNT):
    simulatorThreads.append(Simulator(threadID))
for thread in simulatorThreads:
    thread.start()
for thread in simulatorThreads:
    thread.join()
os.system("sudo mn -c")

