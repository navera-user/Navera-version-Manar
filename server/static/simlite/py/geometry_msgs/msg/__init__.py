from _rosmsg import define
Vector3 = define("geometry_msgs", "Vector3", "float64 x\nfloat64 y\nfloat64 z")
Point = define("geometry_msgs", "Point", "float64 x\nfloat64 y\nfloat64 z")
Quaternion = define("geometry_msgs", "Quaternion", "float64 x\nfloat64 y\nfloat64 z\nfloat64 w 1.0")
Twist = define("geometry_msgs", "Twist", "Vector3 linear\nVector3 angular")
TwistStamped = define("geometry_msgs", "TwistStamped", "std_msgs/Header header\nTwist twist")
