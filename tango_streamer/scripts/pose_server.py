#!/usr/bin/env python

"""
A simple echo server
"""

import socket
import rospy
from sensor_msgs.msg import CompressedImage, PointCloud
from geometry_msgs.msg import PoseStamped, Point32
from std_msgs.msg import Float64, Float64MultiArray
import sys
from tf.transformations import euler_from_quaternion, quaternion_from_euler
from math import pi
import tf

pub_pose = rospy.Publisher('/tango_pose', PoseStamped, queue_size=10)
pub_angles = rospy.Publisher('/tango_angles', Float64MultiArray, queue_size=10)
pub_clock = rospy.Publisher('/tango_clock', Float64, queue_size=10)

""" Keeps track of whether we have a valid clock offset between
    ROS time and Tango time.  We don't care too much about
    how close these two are synched, we mostly just care that
    all nodes use the same offset """
tango_clock_valid = False
tango_clock_offset = -1.0

rospy.init_node("pose_server")

host = ''
port = 11113
backlog = 5
size = 1024
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((host,port))
s.listen(backlog)
all_data = ''
begin_pose_marker = 'POSESTARTINGRIGHTNOW\n' 
end_pose_marker = 'POSEENDINGRIGHTNOW\n'

br = tf.TransformBroadcaster()
while True:
    client, address = s.accept()
    while True:
        try:
            data = client.recv(size)
            if not data:
                break
            all_data += data
            index = all_data.find(end_pose_marker)
            try:
                if index != -1:
                    start = all_data.find(begin_pose_marker)
                    pose = all_data[start+len(begin_pose_marker):index]
                    pose_vals = pose.split(",")
                    print pose_vals
                    tango_timestamp = pose_vals[-1]
                    pose_vals = pose_vals[0:-1]

                    ROS_timestamp = rospy.Time.now()
                    if not(tango_clock_valid):
                        tango_clock_offset = ROS_timestamp.to_time() - float(tango_timestamp)
                        tango_clock_valid = True

                    # publish the offset so other servers can find out about it
                    pub_clock.publish(tango_clock_offset)

                    msg = PoseStamped()
                    # might need to revisit time stamps
                    msg.header.stamp = rospy.Time.now()
                    msg.header.frame_id = 'odom'

                    msg.pose.position.x = float(pose_vals[0])
                    msg.pose.position.y = float(pose_vals[1])
                    msg.pose.position.z = float(pose_vals[2])

                    # two of the rotation axes seem to be off...
                    # we are fixing this in a hacky way right now
                    euler_angles = euler_from_quaternion(pose_vals[3:])
                    pose_vals[3:] = quaternion_from_euler(euler_angles[1],
                                                          euler_angles[0]+pi/2, # this is right
                                                          euler_angles[2]-pi/2)
                    euler_angles_transformed = euler_from_quaternion(pose_vals[3:])
                    msg2 = Float64MultiArray(data=euler_angles_transformed)
                    pub_angles.publish(msg2)

                    msg.pose.orientation.x = float(pose_vals[3])
                    msg.pose.orientation.y = float(pose_vals[4])
                    msg.pose.orientation.z = float(pose_vals[5])
                    msg.pose.orientation.w = float(pose_vals[6])

                    euler_angles_depth_camera = (euler_angles_transformed[0],
                                                 euler_angles_transformed[1],
                                                 euler_angles_transformed[2])
                    pub_pose.publish(msg)
                    br.sendTransform((msg.pose.position.x,
                                      msg.pose.position.y,
                                      msg.pose.position.z),
                                     quaternion_from_euler(euler_angles_depth_camera[0],
                                                           euler_angles_depth_camera[1],
                                                           euler_angles_depth_camera[2]),
                                     rospy.Time.now(),
                                     "device",          # this should be something different like "device"
                                     "odom")
                    all_data = all_data[index+len(end_pose_marker):]
            except Exception as e:
                print e
                # assume we had a bogus message
                all_data = ""
                print "ERROR!!!!!"
        except socket.error, msg:
            sys.stderr.write('ERROR: %s\n' % msg)
            #probably got disconnected
            all_data = ''
            print "DISCONNECTED"
            break
    tango_clock_valid = False
    tango_clock_offset = -1.0
    client.close()
