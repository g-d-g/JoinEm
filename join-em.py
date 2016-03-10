#!/usr/bin/env python
import logging
import fiona
from shapely.geometry import shape, Point, LineString, mapping
from haversine import haversine

def join_em(source_path, destination_path, tolerance=0.0001, 
    haversine_distance=False, combine=True):
    """
    Read a shapefile containing a bunch of linestrings, 
    try and match up the ends and create one long linestring
    """
    src_segments = []
    with fiona.open(source_path, 'r') as source:
        schema = source.schema.copy()
        source_crs = source.crs
        for feature in source:
            if feature['geometry']:
                geometry = shape(feature['geometry'])
                src_segments.append(geometry)

    seg = src_segments.pop()
    segments_in_order = [seg]
    while len(src_segments) > 0:
        start = Point(seg.coords[0])
        end = Point(seg.coords[-1])
    #look for a segment adjact to the end point
        closest_segment, start_or_end, distance = find_closest(end, src_segments,
         haversine_distance=haversine_distance)
        if closest_segment and distance < tolerance:
            logging.debug("Found segment adjacent to end, distance:%f to %s" % 
                (distance, start_or_end))
            src_segments.remove(closest_segment)
            if start_or_end == "end":
                logging.debug("Flipping segment")
                closest_segment.coords = list(closest_segment.coords)[::-1]
            segments_in_order.append(closest_segment)
            seg = closest_segment
        else: # Look for a segment adjactent to the start point
            end_distance = distance
            closest_segment, start_or_end, distance = find_closest(start, src_segments, 
                haversine_distance=haversine_distance)
            if closest_segment and distance < tolerance:
                logging.debug("Found segment adjacent to start, distance:%f to %s" % 
                    (distance, start_or_end))
                src_segments.remove(closest_segment)
                if start_or_end == "start":
                    logging.debug("Flipping segment")
                    closest_segment.coords = list(closest_segment.coords)[::-1]
                segments_in_order.insert(0, closest_segment)
                seg = closest_segment
            else:
                logging.error("Can't find a segment adjacent to start or end segment, giving up")
                logging.error("closest distance to start:%f to end:%f" % (distance, end_distance))
                break

    logging.info( "finished, segments in order:%i remaining segments:%i" 
        % (len(segments_in_order), len(src_segments)))

    if combine:
        logging.debug("Concatenating list of points")
        all_coords = []
        for seg in segments_in_order:
            all_coords.extend(seg.coords)

        logging.debug("Creating result feature")
        result_feature = LineString(all_coords)

        logging.info("Writing combined output to %s" % (destination_path,))
        schema = { 'geometry': 'LineString', 'properties': {} }
        with fiona.collection(destination_path, "w", 
            driver="ESRI Shapefile", 
            crs=source_crs,
            schema=schema) as output:
            output.write({'properties':{}, "geometry":mapping(result_feature)})
    else:
        logging.info("Writing output to %s" % (destination_path,))
        schema = { 'geometry': 'LineString', 'properties': {} }
        with fiona.collection(destination_path, "w", 
            driver="ESRI Shapefile", 
            crs=source_crs,
            schema=schema) as output:
            for seg in segments_in_order:
                output.write({'properties':{}, "geometry":mapping(seg)})


def find_closest(point, segments, haversine_distance=False):
    """
    Find the linestring in segments that has a start or end point closest to point.

    return (segment, start or end, distance)
    """
    closest_segment = None
    closest_distance = 0
    closest_location = None
    for seg in segments:
        start = Point(seg.coords[0])
        end = Point(seg.coords[-1])
        if haversine_distance:
            start_distance = haversine((start.y, start.x), (point.y, point.x)) * 1000
            end_distance = haversine((end.y, end.x), (point.y, point.x)) * 1000
        else:
            start_distance = point.distance(start)
            end_distance = point.distance(end)

        if closest_segment is None or start_distance < closest_distance:
            closest_distance = start_distance
            closest_segment = seg
            closest_location = "start"

        if end_distance < closest_distance:
            closest_distance = end_distance
            closest_segment = seg
            closest_location = "end"

    return closest_segment, closest_location, closest_distance


def _main():
    from optparse import OptionParser
    from shutil import rmtree
    import os
    import shutil
    import sys

    usage = "usage: %prog src.shp dest.shp"
    parser = OptionParser(usage=usage,
                          description="")
    parser.add_option("-d", "--debug", action="store_true", dest="debug",
                      help="Turn on debug logging")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet",
                      help="turn off all logging")
    parser.add_option("-t", "--tolerance", action="store", type="float",
        dest='tolerance', default="0.0001",
        help="max distance between start end points of segments to be considered connected")
    parser.add_option("-O", "--overwrite", action="store_true", dest="overwrite",
                      help="overwrite existing file")
    parser.add_option("-c", "--combine", action="store_true", dest="combine",
                      help="Combine features into a single line, otherwise they will just be put into order")
    parser.add_option("-m", "--meters", action="store_true", dest="haversine",
                      help="Use haversine formula for distance, tolerance is in meters")
    (options, args) = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if options.debug else
    (logging.ERROR if options.quiet else logging.INFO),
        format='%(message)s')

    if len(args) != 2:
        logging.error("2 args needed")
        sys.exit(-1)

    src, dest = args
    if not os.path.exists(src):
        logging.error("source file does not exist")
        sys.exit(-1)

    if os.path.exists(dest):
        if options.overwrite:
            shutil.rmtree(dest)
        else:
            logging.error("Destination already exists. Will not overwrite")
            sys.exit(-1)

    join_em(src, dest, tolerance=options.tolerance, 
        haversine_distance=options.haversine,
        combine=options.combine)

if __name__ == "__main__":
    _main()
