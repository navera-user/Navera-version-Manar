from _rosmsg import define
FloatingPointRange = define("rcl_interfaces", "FloatingPointRange", "float64 from_value\nfloat64 to_value\nfloat64 step")
IntegerRange = define("rcl_interfaces", "IntegerRange", "int64 from_value\nint64 to_value\nuint64 step")
ParameterDescriptor = define("rcl_interfaces", "ParameterDescriptor", """string name
uint8 type
string description
string additional_constraints
bool read_only
bool dynamic_typing
FloatingPointRange[] floating_point_range
IntegerRange[] integer_range""")
