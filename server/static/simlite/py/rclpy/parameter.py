class Parameter:
    class Type:
        NOT_SET, BOOL, INTEGER, DOUBLE, STRING = range(5)

    def __init__(self, name, type_=None, value=None):
        self.name = name
        self.value = value

    def get_parameter_value(self):
        return self
