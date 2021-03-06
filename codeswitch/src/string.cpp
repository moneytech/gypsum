// Copyright Jay Conrod. All rights reserved.

// This file is part of CodeSwitch. Use of this source code is governed by
// the 3-clause BSD license that can be found in the LICENSE.txt file.


#include "string.h"

#include <algorithm>
#include <cstring>
#include "array.h"
#include "block.h"
#include "error.h"
#include "handle.h"
#include "heap.h"
#include "utils.h"

using namespace std;

namespace codeswitch {
namespace internal {

word_t String::sizeForLength(length_t length) {
  ASSERT(length <= kMaxLength);
  return elementsOffset(sizeof(String), sizeof(u8)) + length;
}


void* String::operator new (size_t, Heap* heap, length_t length) {
  ASSERT(length <= kMaxLength);
  auto size = sizeForLength(length);
  auto string = reinterpret_cast<String*>(heap->allocate(size));
  string->length_ = length;
  return string;
}


String::String(const u8* chars)
    : Object(STRING_BLOCK_TYPE) {
  copy_n(chars, length_, chars_);
}


String::String(const char* chars)
    : Object(STRING_BLOCK_TYPE) {
  copy_n(reinterpret_cast<const u8*>(chars), length_, chars_);
}


String::String()
    : Object(STRING_BLOCK_TYPE) { }


Local<String> String::create(Heap* heap, length_t length, const u8* chars) {
  RETRY_WITH_GC(heap, return Local<String>(new(heap, length) String(chars)));
}


Local<String> String::create(Heap* heap, length_t length, const char* chars) {
  RETRY_WITH_GC(heap, return Local<String>(new(heap, length) String(chars)));
}


Local<String> String::create(Heap* heap, length_t length) {
  RETRY_WITH_GC(heap, return Local<String>(new(heap, length) String));
}


String* String::rawFromUtf8CString(Heap* heap, const u8* chars) {
  length_t length = strlen(reinterpret_cast<const char*>(chars));
  ASSERT(length <= kMaxLength);
  return new(heap, length) String(chars);
}


String* String::rawFromUtf8CString(Heap* heap, const char* chars) {
  return rawFromUtf8CString(heap, reinterpret_cast<const u8*>(chars));
}


Local<String> String::fromUtf8CString(Heap* heap, const u8* chars) {
  length_t length = strnlen(reinterpret_cast<const char*>(chars), kMaxLength);
  return create(heap, length, chars);
}


Local<String> String::fromUtf8String(Heap* heap, const std::string& stlString) {
  ASSERT(stlString.size() <= kMaxLength);
  return create(heap, stlString.size(), stlString.data());
}


Local<String> String::fromUtf8String(Heap* heap, const u8* chars, length_t length) {
  return create(heap, length, chars);
}


Local<String> String::fromUtf8CString(Heap* heap, const char* utf8Chars) {
  return fromUtf8CString(heap, reinterpret_cast<const u8*>(utf8Chars));
}


Local<String> String::fromUtf8String(Heap* heap, const char* utf8Chars, length_t length) {
  return fromUtf8String(heap, reinterpret_cast<const u8*>(utf8Chars), length);
}


vector<u8> String::toUtf8StlVector() const {
  return vector<u8>(chars_, chars_ + length_);
}


string String::toUtf8StlString() const {
  return string(reinterpret_cast<const char*>(chars_), length_);
}


bool String::equals(const String* other) const {
  if (length() != other->length())
    return false;
  for (length_t i = 0; i < length(); i++) {
    if (get(i) != other->get(i))
      return false;
  }
  return true;
}


bool String::equals(const u8* other) const {
  length_t i;
  for (i = 0; i < length() && other[i] != '\0'; i++) {
    if (get(i) != other[i])
      return false;
  }
  return other[i] == '\0';
}


bool String::equals(const char* other) const {
  return equals(reinterpret_cast<const u8*>(other));
}


int String::compare(String* other) const {
  auto minLength = min(length(), other->length());
  int cmp;
  for (length_t i = 0; i < minLength; i++) {
    cmp = static_cast<int>(get(i)) - static_cast<int>(other->get(i));
    if (cmp != 0)
      return cmp;
  }
  cmp = static_cast<int>(length()) - static_cast<int>(other->length());
  return cmp;
}


u32 String::hashCode() const {
  u32 code = 0;
  for (auto ch : *this)
    code = 31 * code + ch;
  return code;
}


String* String::tryConcat(String* other) {
  if (other->length_ == 0) {
    return this;
  } else if (length_ == 0) {
    return other;
  }

  auto consLength = length_ + other->length_;
  if (consLength > kMaxLength)
    throw Error("maximum string length exeeded in concatenation");

  auto cons = new(getHeap(), consLength) String;
  copy_n(chars_, length_, cons->chars_);
  copy_n(other->chars_, other->length_, cons->chars_ + length_);
  return cons;
}


Local<String> String::concat(const Handle<String>& left,
                             const Handle<String>& right) {
  RETRY_WITH_GC(left->getHeap(), return Local<String>(left->tryConcat(*right)));
}


String* String::trySubstring(length_t begin, length_t end) const {
  ASSERT(begin <= end && end <= length());
  auto len = end - begin;
  auto beginChars = chars() + begin;
  return new(getHeap(), len) String(beginChars);
}


Local<String> String::substring(const Handle<String>& string,
                                length_t begin, length_t end) {
  RETRY_WITH_GC(string->getHeap(), return Local<String>(string->trySubstring(begin, end)));
}


length_t String::find(u8 needle, length_t start) const {
  ASSERT(start <= length());

  for (length_t i = start; i < length(); i++) {
    if (get(i) == needle)
      return i;
  }
  return kIndexNotSet;
}


length_t String::find(String* needle, length_t start) const {
  ASSERT(start <= length());
  if (start + needle->length() > length())
    return kIndexNotSet;

  // TODO: use Knuth-Morris-Pratt for sufficiently large needles and haystacks.
  for (length_t i = start; i < length() - needle->length() + 1; i++) {
    bool found = true;
    for (length_t j = 0; found && j < needle->length(); j++) {
      found = get(i + j) == needle->get(j);
    }
    if (found)
      return i;
  }
  return kIndexNotSet;
}


length_t String::count(u8 needle) const {
  length_t pos = 0;
  length_t count = 0;
  while ((pos = find(needle, pos)) != kIndexNotSet) {
    count++;
    pos++;
  }
  return count;
}


length_t String::count(String* needle) const {
  if (needle->isEmpty()) {
    // Special case to ensure termination: there is an empty string between every character,
    // and at the beginning and end of the string.
    return length() + 1;
  }

  length_t pos = 0;
  length_t count = 0;
  while ((pos = find(needle, pos)) != kIndexNotSet) {
    count++;
    pos += needle->length();
  }
  return count;
}


Local<BlockArray<String>> String::split(Heap* heap, const Handle<String>& string, u8 sep) {
  auto count = string->count(sep);
  auto pieces = BlockArray<String>::create(heap, count + 1);
  length_t pos = 0;
  for (length_t i = 0; i < count; i++) {
    auto next = string->find(sep, pos);
    auto sub = String::substring(string, pos, next);
    pieces->set(i, *sub);
    pos = next + 1;
  }
  auto sub = String::substring(string, pos, string->length());
  pieces->set(count, *sub);
  return pieces;
}


Local<BlockArray<String>> String::split(Heap* heap,
                                        const Handle<String>& string,
                                        const Handle<String>& sep) {
  if (sep->isEmpty()) {
    // Special case: if the separator is empty, we return an array of single-character strings.
    auto pieces = BlockArray<String>::create(heap, string->length());
    for (length_t i = 0; i < string->length(); i++) {
      auto ch = string->get(i);
      auto piece = create(heap, 1, &ch);
      pieces->set(i, *piece);
    }
    return pieces;
  }

  auto count = string->count(*sep);
  auto pieces = BlockArray<String>::create(heap, count + 1);
  length_t pos = 0;
  for (length_t i = 0; i < count; i++) {
    auto next = string->find(*sep, pos);
    auto sub = substring(string, pos, next);
    pieces->set(i, *sub);
    pos = next + sep->length();
  }
  auto sub = substring(string, pos, string->length());
  pieces->set(count, *sub);
  return pieces;
}


Local<String> String::join(Heap* heap,
                           const Handle<BlockArray<String>>& strings,
                           const Handle<String>& sep) {
  if (strings->isEmpty()) {
    return fromUtf8CString(heap, "");
  }

  // Calculate the total length of the joined string.
  length_t totalLength = 0;
  for (auto str : **strings) {
    totalLength += str->length();
  }
  totalLength += (strings->length() - 1) * sep->length();

  // Allocate a string and fill it in.
  auto joined = create(heap, totalLength);
  auto out = joined->chars_;
  for (length_t i = 0; i < strings->length() - 1; i++) {
    auto str = strings->get(i);
    out = copy(str->chars(), str->chars() + str->length(), out);
    out = copy(sep->chars(), sep->chars() + sep->length(), out);
  }
  auto last = strings->get(strings->length() - 1);
  out = copy(last->chars(), last->chars() + last->length(), out);
  ASSERT(out == joined->chars() + totalLength);

  return joined;
}


bool String::tryToI32(i32* n) const {
  if (isEmpty())
    return false;

  length_t start = 0;
  i64 sign = 1;
  if (get(0) == '-') {
    sign = -1;
    start = 1;
  } else if (get(0) == '+') {
    start = 1;
  }
  if (start == length())
    return false;

  i64 value = 0;
  i64 limit = sign < 0 ? -static_cast<i64>(INT32_MIN) : INT32_MAX;
  for (length_t i = start; i < length(); i++) {
    auto d = get(i);
    if (!inRange<u8>(d, '0', '9'))
      return false;
    auto v = d - '0';
    value = 10 * value + v;
    if (value > limit)
      return false;
  }
  ASSERT(INT32_MIN <= sign * value && sign * value <= INT32_MAX);
  *n = static_cast<i32>(sign * value);
  return true;
}


u8 String::iterator::operator * () const {
  return str_->get(index_);
}


bool String::iterator::operator == (const iterator& other) const {
  return str_ == other.str_ && index_ == other.index_;
}


bool String::iterator::operator != (const iterator& other) const {
  return !(*this == other);
}


bool String::iterator::operator < (const iterator& other) const {
  return str_ == other.str_ && index_ < other.index_;
}


bool String::iterator::operator <= (const iterator& other) const {
  return str_ == other.str_ && index_ <= other.index_;
}


bool String::iterator::operator > (const iterator& other) const {
  return str_ == other.str_ && index_ > other.index_;
}


bool String::iterator::operator >= (const iterator& other) const {
  return str_ == other.str_ && index_ >= other.index_;
}


String::iterator String::iterator::operator + (ssize_t offset) const {
  iterator copy(*this);
  return copy += offset;
}


String::iterator& String::iterator::operator += (ssize_t offset) {
  ssize_t index = static_cast<ssize_t>(index_) + offset;
  ASSERT(index >= 0);
  index_ = static_cast<length_t>(index);
  return *this;
}


String::iterator& String::iterator::operator ++ () {
  return *this += 1;
}


String::iterator String::iterator::operator - (ssize_t offset) const {
  return *this + -offset;
}


String::iterator& String::iterator::operator -= (ssize_t offset) {
  return *this += -offset;
}


String::iterator& String::iterator::operator -- () {
  return *this += -1;
}


String::iterator String::begin() const {
  return iterator(this, 0);
}


String::iterator String::end() const {
  return iterator(this, length());
}


ostream& operator << (ostream& os, const String* str) {
  os << brief(str)
     << "\n  chars: " << str->toUtf8StlString();
  return os;
}

}
}
