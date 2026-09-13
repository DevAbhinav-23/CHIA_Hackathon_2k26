
func.func @dynamicArrayVariable() {
  // expected-error @below {{failed to legalize operation 'moore.variable'}}
  %var = moore.variable : <!moore.open_uarray<i32>>
  return
}
