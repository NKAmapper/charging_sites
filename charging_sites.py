#!/usr/bin/env python3
# -*- coding: utf8


import sys
import json
import math
import copy
import re
import urllib.request, urllib.error, urllib.parse
from collections import Counter
sys.path.append('../gml/')
import gml2osm


max_sample = 5000  # Break down the globe into grids of max this number of charging stations 
max_gap = 20       # Max distance between charge points for a cluster
min_common = 0.5   # Min proportion of identical values for group tag

single_analysis = "capacity"  # Alternatives for single station analysis: "capacity", "socket", "output"

overpass_api = "https://overpass-api.de/api/interpreter"  # Overpass endpoint
#overpass_api = "https://overpass.kumi.systems/api/interpreter"



# Output message

def message (output_text):

	sys.stdout.write (output_text)
	sys.stdout.flush()



# Compute approximation of distance between two coordinates, in meters.
# Works for short distances
# Format: (lon, lat)

def distance (p1, p2):

	lon1, lat1, lon2, lat2 = map(math.radians, [p1[0], p1[1], p2[0], p2[1]])
	x = (lon2 - lon1) * math.cos( 0.5*(lat2+lat1) )
	y = lat2 - lat1
	return 6371000 * math.sqrt( x*x + y*y )



# Return most common name from given list of names.
# The chosen name must appear in at least given minimum proportion of the list.

def common (names):
	if names:
		name_counter = Counter(names)
		name = name_counter.most_common(1)
		if len(name) == 1 and name[0][1] > len(names) * min_common:
			return name[0][0]

	return ""



# Identify groups of chargers within given distance.
# Recursive splitting into smaller bbox until acceptable size.

def identify_groups(chargers, level):

	global count_down

	# Recursively split into smaller halfs until until sufficiently small number of chargers

	if len(chargers) > max_sample:

		# Get which axis to split in half

		min_bbox = [0, 0]
		max_bbox = [0, 0]
		for i in [0,1]:
			min_bbox[i] = min(stations[ charger ]['point'][i] for charger in chargers)
			max_bbox[i] = max(stations[ charger ]['point'][i] for charger in chargers)				

		if distance(min_bbox, (min_bbox[0], max_bbox[1])) > distance(min_bbox, (max_bbox[0], min_bbox[1])):
			axis = 1
		else:
			axis = 0

		center = 0.5 * (max_bbox[ axis ] + min_bbox[ axis ])

		# Split chargers and recursively swap

		chargers1 = [ charger for charger in chargers if stations[ charger ]['point'][ axis ] < center ]
		chargers2 = [ charger for charger in chargers if stations[ charger ]['point'][ axis ] >= center ]
		groups = identify_groups(chargers1, level+1) + identify_groups(chargers2, level+1)

		return groups


	# Identify groups

	groups = []

	for charger1 in chargers:

		found_group = None

		if (stations[ charger1 ]['type'] == "relation"
			or ("capacity" in stations[ charger1 ]['tags']
				 	and stations[ charger1 ]['tags']['capacity'].isnumeric()
					and int(stations[ charger1 ]['tags']['capacity']) > 2)):
				continue

		for group in groups[:]:
			for charger2 in group:
				d = distance(stations[ charger1 ]['point'], stations[ charger2 ]['point'])
				if d < max_gap:
					if found_group is None:
						group.add(charger1)
						found_group = group

					else:
						found_group.update(group)
						groups.remove(group)
					break

		if found_group is None:
			groups.append(set({ charger1 }))

	count_down -= len(chargers)
	message ("\r\t%i " % count_down)

	return groups



# Main program

if __name__ == '__main__':

	message ("\nAnalyzing OSM charging stations\n\n")

	stations = {}
	points = []

	# Load OSM charging stations

	if not "--noload" in sys.argv:
		# Load all charging stations from OSM

		message ("Loading from Overpass ...\n")
		query = ('[out:json][timeout:600];'
				'('
					'nwr["amenity"="charging_station"];'
					'nwr["man_made"="charge_point"];'
				')->.a;'
				'(.a; .a>; .a<;);'
				'out center meta;')

		request = urllib.request.Request(overpass_api + "?data=" + urllib.parse.quote(query))
		file = urllib.request.urlopen(request)
		osm_data = json.load(file)
		elements = osm_data['elements']
		file.close()

		# Store for later quick rerun if successful retrieval
		if len(elements) > 90000:
			file = open("global_stations.json", "w")
			json.dump(osm_data, file, indent=1, ensure_ascii=False)
			file.close()

	else:
		# Load charging stations from earlier retrieval

		message ("Loading from file ...\n")
		file = open("global_stations.json")
		osm_data = json.load(file)
		file.close()
		elements = osm_data['elements']

	message ("\t%i element loaded\n" % len(elements))

	# Store charging stations in stations dict

	count_charge_points = 0
	for element in elements:
		if "tags" in element and "amenity" in element['tags'] and element['tags']['amenity'] == "charging_station":
			if "center" in element:
				point = (element['center']['lon'], element['center']['lat'])  # Center of areas
			else:
				point = (element['lon'], element['lat'])
			element['point'] = point
			stations[ element['id'] ] = element
			points.append(element['id'])

		if "tags" in element and "man_made" in element['tags'] and element['tags']['man_made'] == "charge_point":
			count_charge_points += 1		

	if not stations:
		sys.exit("\tNo stations")

	message ("\t%i charging stations, %i charge points found\n" % (len(stations), count_charge_points))

	# Identify groups

	message ("\nIdentifying groups ...\n")
	count_down = len(points)

	groups = identify_groups(points, 0)
	message ("\r\tFound %i sites\n" % len(groups))

	single = sum(len(group) == 1 for group in groups)
	message ("\tTotal %i charge points in %i groups\n\n" % (len(stations) - single, len(groups) - single))

	# Produce OSM file with identified groups

	osm_id = -1000

	for group in groups:
		if len(group) == 1:
			continue

		# Location of new amenity=charging_station node will be center of group
		lon = sum([stations[ station ]['point'][0] for station in group]) / len(group)
		lat = sum([stations[ station ]['point'][1] for station in group]) / len(group)

		osm_id -= 1
		new_element = {
			'id': osm_id,
			'type': 'node',
			'lon': lon,
			'lat': lat,
			'action': 'modify',
			'tags': {
				'amenity': 'charging_station',
				'GROUP': str(len(group))
			}
		}

		# Prepare for determining some of the group tags

		names = []
		brands = []
		operators = []

		sockets = {}
		capacity = 0
		capacity_not_found = False

		# Collect tag information from each charge point in group

		for station in group:
			charger = stations[ station ]

			# Replace feature tag for charge points

			del charger['tags']['amenity']
			charger['tags']['MAN_MADE'] = "CHARGE_POINT"
			charger['action'] = "modify"

			# Collect name, brand and operator to detmine common tags

			if "name" in charger['tags']:
				names.append(charger['tags']['name'])
			if "brand" in charger['tags']:
				brands.append(charger['tags']['brand'])
			if "operator" in charger['tags']:
				operators.append(charger['tags']['operator'])

			# Accumulate capacity for each charge point but do not use if one is missing

			if "capacity" in charger['tags'] and charger['tags']['capacity'].isnumeric():
				capacity += int(charger['tags']['capacity'])
			else:
				capacity_not_found = True

			# Collect socket information

			for key, value in iter(charger['tags'].items()):

				# Accumulate number of sockets for group

				if key.split(":")[0] == "socket" and len(key.split(":")) == 2:
					value2 = value.split(" ")[0]
					if value2.isnumeric():
						value2 = int(value2)
						if value2 < 11:
							socket_type = key.split(":")[1]
							if socket_type not in sockets:
								sockets[ socket_type ] = {
									'count': 0,
									'output': 0
								} 
							sockets[ socket_type ]['count'] += value2

				# Identify max socket output (kW) for group

				if "socket:" in key and ":output" in key and len(key.split(":")) == 3:
					value2 = re.findall('\d+', value)
					if value2 and value2[0].isnumeric():
						value2 = int(value2[0])
						socket_type = key.split(":")[1]
						if socket_type not in sockets:
							sockets[ socket_type ] = {
								'count': 0,
								'output': 0
							} 
						sockets[ socket_type ]['output'] = max(value2, sockets[ socket_type ]['output'])

		# Assign tag suggestions for the group

		if capacity > 0 and not capacity_not_found:
			new_element['tags']['capacity'] = str(capacity)

		for socket_type in sockets:
			socket = sockets[ socket_type ]
			if socket['count'] > 0:
				new_element['tags']["socket:" + socket_type] = str(socket['count'])
				new_element['action'] = "modify"
			if socket['output'] > 0:
				new_element['tags']["socket:" + socket_type + ":output"] = str(socket['output']) + " kW"
				new_element['action'] = "modify"

		# Suggest name, operator and brand tags based on most common values in group

		name = common(names)
		if name:
			new_element['tags']['name'] = name
		operator = common(operators)
		if operator:
			new_element['tags']['operator'] = operator
		brand = common(brands)
		if brand:
			new_element['tags']['brand'] = brand

		# Create new amenity=charging_station node for group

		elements.append(new_element)

	# Save generated OSM file

	filename = "global_charger_groups.osm"
	gml2osm.save_osm(elements, filename, generator="charging_analysis", verbose=True)

	# Output summary of groups for different charge point sizes

	message ("\nNumber of groups for each charge point size:\n")

	largest = max(len(group) for group in groups)

	for i in range(1, largest+1):
		count = sum(len(group) == i for group in groups)
		percent = 100.0 * count * i / len(stations)
		if count > 0:
			message ("\t%6i  %6i  %6i  %4.1f%%\n" %(i, count, i * count, percent))

	# Output capacity statistics for single charging stations

	capacities = {}
	for group in groups:
		if len(group) == 1:
			capacity = 0
			charger = stations[ list(group)[0] ]

			# Alternative 1: Accumulate capacity

			if single_analysis == "capacity":
				if "capacity" in charger['tags']:
					if charger['tags']['capacity'].isnumeric():
						capacity = int(charger['tags']['capacity'])

			# Alternative 2: Accumulate total number of sockets (across socket types)

			elif single_analysis == "socket":
				for key, value in iter(charger['tags'].items()):
					if key.split(":")[0] == "socket" and len(key.split(":")) == 2:
						value2 = value.split(" ")[0]
						if value2.isnumeric():
							capacity = max(capacity, int(value2))

			# Alternative 3: Identify max power (kW)

			elif single_analysis == "output":
				for key, value in iter(charger['tags'].items()):
					if "socket:" in key and ":output" in key:
						value2 = re.findall('\d+', value)
						if value2 and value2[0].isnumeric():
							capacity = max(capacity, int(value2[0]))

			if capacity > 0:
				if capacity not in capacities:
					capacities[ capacity ] = 0
				capacities[ capacity ] += 1

	largest = max(capacities.keys())
	total = sum(capacities.values())

	message ("\nTotal %i points with %s tag in single groups\n" % (total, single_analysis))

	for i in range(1, largest+1):
		if i in capacities:
			percent = 100.0 * capacities[i] / total
			message ("\t%6i   %6i  %4.1f%%\n" % (i, capacities[i], percent))

	message ("\nDone\n\n")
	