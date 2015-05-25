// Copyright 2014-2015 Jay Conrod. All rights reserved.

// This file is part of CodeSwitch. Use of this source code is governed by
// the 3-clause BSD license that can be found in the LICENSE.txt file.


#include "field.h"

#include "block.h"
#include "handle.h"
#include "heap.h"
#include "type.h"

using namespace std;

namespace codeswitch {
namespace internal {

#define FIELD_POINTERS_LIST(F) \
  F(Field, name_)              \
  F(Field, type_)              \

DEFINE_POINTER_MAP(Field, FIELD_POINTERS_LIST)

#undef FIELD_POINTERS_LIST


void* Field::operator new (size_t, Heap* heap) {
  return reinterpret_cast<Field*>(heap->allocate(sizeof(Field)));
}


Field::Field(Name* name, u32 flags, Type* type)
    : Block(FIELD_BLOCK_TYPE),
      name_(this, name),
      flags_(flags),
      type_(this, type) { }


Local<Field> Field::create(Heap* heap, const Handle<Name>& name,
                           u32 flags, const Handle<Type>& type) {
  RETRY_WITH_GC(heap, return Local<Field>(new(heap) Field(*name, flags, *type)));
}


ostream& operator << (ostream& os, const Field* field) {
  os << brief(field)
     << "\n  name: " << brief(field->name())
     << "\n  type: " << brief(field->type());
  return os;
}

}
}
