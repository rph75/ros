#!/usr/bin/env python

from math import cos, sin
import rospy
import tf
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Point, Pose, Quaternion, Twist, Vector3
from motorctrl.srv import motorctrl_readspeed, motorctrl_readspeedResponse, motorctrl_readpos, motorctrl_readposResponse, motorctrl_writepos, motorctrl_writeposResponse, motorctrl_writespeed, motorctrl_writespeedResponse
from odometry_data import Converter, enc_per_m


class Node:
    def callback(self,timer_event):
        current_time = rospy.Time.now()
        motorctrl_readpos_response=self.motorctrl_readpos_proxy()
        encoder=motorctrl_readpos_response.encoder
        if self.last_encoder is not None:
            #This is not the first time the loop is called - can do something usefil

            enc_diff = []
            for new, old in zip(encoder, self.last_encoder):
                enc_diff.append(new - old)

            # TODO: we could also use the encoder's time, and use that time to publish - but then how to avoid drift?
            dt = (current_time - self.last_time).to_sec()
            #Compute left and right as average of front and back wheels
            enc_diff_left = (enc_diff[0]+enc_diff[1])/2
            enc_diff_right = (enc_diff[2]+enc_diff[3])/2
            enc_delta = (enc_diff_right-enc_diff_left)/2
            #Compute mid speed as average of left and right
            enc = (enc_diff_right+enc_diff_left)/2
            #print "enc_delta={}, enc={}".format(enc_delta, enc)
            speed = enc/enc_per_m/dt
            delta = enc_delta/enc_per_m/dt
            # Now look up the point for angular speed and path speed
            #print "looking up speed={}, delta={}".format(speed,delta)
            path,ang = self.converter.find(speed,delta) #path in m/s, ang in rad/s
            #print "found path={} m/s, ang={} rad/sec".format(path, ang)
            # compute odometry in a typical way given the velocities of the robot
            delta_x = (path * cos(self.th)) * dt
            delta_y = (path * sin(self.th)) * dt
            delta_th = ang * dt

            self.x += delta_x
            self.y += delta_y
            self.th += delta_th

            # since all odometry is 6DOF we'll need a quaternion created from yaw
            odom_quat = tf.transformations.quaternion_from_euler(0, 0, self.th)

            # first, we'll publish the transform over tf
            self.odom_broadcaster.sendTransform(
                (self.x, self.y, 0.),
                odom_quat,
                current_time,
                "base_link",
                "odom"
            )

            # next, we'll publish the odometry message over ROS
            odom = Odometry()
            odom.header.stamp = current_time
            odom.header.frame_id = "odom"

            # set the position
            odom.pose.pose = Pose(Point(self.x, self.y, 0.), Quaternion(*odom_quat))

            # set the velocity
            odom.child_frame_id = "base_link"
            odom.twist.twist = Twist(Vector3(path, 0, 0), Vector3(0, 0, ang))

            # publish the message
            self.odom_pub.publish(odom)


        self.last_encoder = encoder
        self.last_time = current_time

    # Power on and prepare for general usage.
    # This will activate the device and take it out of sleep mode (which must be done
    # after start-up). This function also sets both the accelerometer and the gyroscope
    # to default range settings, namely +/- 2g and +/- 250 degrees/sec.
    def __init__(self):
        # Initialize the node and name it.
        rospy.init_node('odom_node')

        rospy.loginfo(rospy.get_name() + " Waiting for service /motorctrl_service/* ...")
        rospy.wait_for_service('/motorctrl_service/readpos')
        rospy.wait_for_service('/motorctrl_service/readspeed')
        rospy.loginfo(rospy.get_name() + " Found service /motorctrl_service/* .")

        self.motorctrl_readpos_proxy = rospy.ServiceProxy('/motorctrl_service/readpos', motorctrl_readpos)
        self.odom_pub = rospy.Publisher("odom", Odometry, queue_size=50)
        self.odom_broadcaster = tf.TransformBroadcaster()

        #define start coordinates
        self.x=0
        self.y=0
        self.th=0
        self.last_encoder=None
        self.converter = Converter()
        period_secs = 0.050
        interval = rospy.Duration.from_sec(period_secs)
        rospy.Timer(interval, self.callback)
        rospy.loginfo(rospy.get_name() + " started odom_node.")
        rospy.spin()

# Main function.
if __name__ == '__main__':
    node = Node()

