# -*- coding: utf-8 -*-
"""
Author: Jonathan Balewicz
Date: January 10, 2021

Purpose: Decode data produced by networkSim.py
    
"""

import csv
import copy

FILE_NUMBER = 1
THREAD_COUNT = 10

networks_data = []

for threadID in range(THREAD_COUNT):
	for d in range(FILE_NUMBER):
		file_name = "dataWLatency"+str(d+1)+"t"+threadID+".csv"
		with open(file_name, 'r') as f:
			reader = csv.reader(f)
			for line in reader:
				networks_data.append(copy.deepcopy(line))

		networks_data = [[int(float(j)) for j in i] for i in networks_data]
		network_number = -1
		for network_data in networks_data:
			network_number += 1
			if network_number == 0:
				SIMULATION_COUNT = network_data[0]
				TIME_BETWEEN_PINGS = network_data[1]
				PINGS_PER_WINDOW = network_data[2]
				WINDOW_COUNT = network_data[3]
				LINK_CUT_WINDOW = network_data[4]
				MAX_TRAFFIC_DURATION = network_data[5]
				continue
			node_count = network_data[0]
			central_node_index = network_data[1]

			alarmStart = 2
			latencyMatrixBeforeLinkCutStart = alarmStart + node_count
			latencyMatrixAfterLinkCutStart = latencyMatrixBeforeLinkCutStart + (node_count * LINK_CUT_WINDOW)
			adjMatrixStart = latencyMatrixAfterLinkCutStart + (node_count * (WINDOW_COUNT - LINK_CUT_WINDOW))
			failureAdjMatrixStart = adjMatrixStart + (node_count ** 2)

			# 1 for alarm, 0 for no alarm for each node
			alarm_list = network_data[alarmStart:latencyMatrixBeforeLinkCutStart]
			latency_matrix_before_link_cut_flat = network_data[latencyMatrixBeforeLinkCutStart:
															   latencyMatrixAfterLinkCutStart]
			latency_matrix_after_link_cut_flat = network_data[latencyMatrixAfterLinkCutStart:adjMatrixStart]
			adj_matrix_flat = network_data[adjMatrixStart:failureAdjMatrixStart]
			failure_adj_matrix_flat = network_data[failureAdjMatrixStart:]

			latency_matrix_before_link_cut = []
			latency_matrix_after_link_cut = []
			adj_matrix = []  # failure free matrix
			failure_adj_matrix = []  # matrix with the failure

			i = 0

			for j in range(LINK_CUT_WINDOW):
				latency_matrix_before_link_cut.append([])
				for _ in range(node_count):
					latency_matrix_before_link_cut[j].append(latency_matrix_before_link_cut_flat[i])
					i += 1
			i = 0

			for j in range(WINDOW_COUNT - LINK_CUT_WINDOW):
				latency_matrix_after_link_cut.append([])
				for _ in range(node_count):
					latency_matrix_after_link_cut[j].append(latency_matrix_after_link_cut_flat[i])
					i += 1
			i = 0

			for j in range(node_count):
				adj_matrix.append([])
				for _ in range(node_count):
					adj_matrix[j].append(adj_matrix_flat[i])
					i += 1
			i = 0
			for j in range(node_count):
				failure_adj_matrix.append([])
				for _ in range(node_count):
					failure_adj_matrix[j].append(failure_adj_matrix_flat[i])
					i += 1

			x = 0

			print(alarm_list) # alarms 1 for alarm 0 for no alarm

			# Int array. The [i][j] index is the average latency from the central node to node j, (LINK_CUT_WINDOW - i)
			# windows before the link was cut. The max i is (LINK_CUT_WINDOW - 1) representing the last window before the
			# link was cut. Latency is 0 if the packet was dropped, or the index j is the central node.
			print(latency_matrix_before_link_cut)

			# The [i][j] index is the average latency from the central node to node j, i windows
			# after the link was cut. The max i is (WINDOW_COUNT - 1) representing the last window
			# taken. When i = 0, it represents the first window after the link was cut.
			print(latency_matrix_after_link_cut)

			print(adj_matrix)
			print(failure_adj_matrix)

			#
			# File wide variables:
			# SIMULATION_COUNT,
			# TIME_BETWEEN_PINGS, # in seconds
			# PINGS_PER_WINDOW,
			# WINDOW_COUNT, # total number of windows per network/simulation
			# LINK_CUT_WINDOW, # window where the link was cut before the latency data was taken
			#
			# Network specific variables:
			# node_count,
			# central_node_index,
			# alarm_list,
			# latency_matrix_before_link_cut,
			# latency_matrix_after_link_cut,
			# adj_matrix,
			# failure_adj_matrix
