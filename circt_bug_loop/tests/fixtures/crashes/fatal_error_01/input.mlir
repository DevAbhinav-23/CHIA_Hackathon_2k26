
moore.class.classdecl @ClassWithString {
  moore.class.propertydecl @text : !moore.string
}

func.func @classNewWithString() {
  // expected-error @below {{class struct has member types with no data layout}}
  // expected-error @below {{failed to legalize operation 'moore.class.new'}}
  %h = moore.class.new : <@ClassWithString>
  return
}
