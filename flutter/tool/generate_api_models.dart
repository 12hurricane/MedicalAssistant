// Generates Dart models from the backend's OpenAPI schema.
//
// Run from the `flutter/` directory:
//
//     dart run tool/generate_api_models.dart
//
// Output: lib/core/api/generated/api_models.dart
//
// Why a purpose-built generator rather than a general OpenAPI toolchain: the spec
// this reads uses a small, known set of constructs ($ref, anyOf-with-null for
// optionals, arrays, string enums, one additionalProperties map). A generator scoped
// to those is a few hundred lines, needs no JVM, no build_runner, and no network, and
// it fails loudly on anything it was not built for instead of emitting something
// plausible. `_unsupported` is that tripwire.
//
// The generated file is committed. `test/api_contract_test.dart` regenerates it in
// memory and fails if the committed copy is stale, so a backend schema change cannot
// silently diverge from the client.

import 'dart:convert';
import 'dart:io';

const _defaultSpec = '../backend/openapi.json';
const _defaultOut = 'lib/core/api/generated/api_models.dart';

void main(List<String> args) {
  final specPath = args.isNotEmpty ? args[0] : _defaultSpec;
  final outPath = args.length > 1 ? args[1] : _defaultOut;

  final specFile = File(specPath);
  if (!specFile.existsSync()) {
    stderr.writeln(
      'Cannot find $specPath.\n'
      'Regenerate it from the backend first:\n'
      '  python -c "import json; from app.main import app; '
      'json.dump(app.openapi(), open(\'openapi.json\',\'w\'), indent=2)"',
    );
    exit(1);
  }

  final spec = jsonDecode(specFile.readAsStringSync()) as Map<String, dynamic>;
  final source = generate(spec);

  final out = File(outPath);
  out.parent.createSync(recursive: true);
  out.writeAsStringSync(source);
  stdout.writeln('Wrote $outPath (${source.split('\n').length} lines)');
}

/// Renders the whole models library from a parsed OpenAPI document.
///
/// Pure: same spec in, same string out. The contract test depends on that.
String generate(Map<String, dynamic> spec) {
  final schemas = ((spec['components'] as Map<String, dynamic>?)?['schemas']
          as Map<String, dynamic>?) ??
      const {};

  final enums = <String, List<String>>{};
  final objects = <String, Map<String, dynamic>>{};

  for (final name in schemas.keys.toList()..sort()) {
    final schema = schemas[name] as Map<String, dynamic>;
    if (schema['enum'] is List) {
      if (schema['type'] != 'string') {
        _unsupported('non-string enum in schema "$name"');
      }
      enums[name] = (schema['enum'] as List).cast<String>();
    } else {
      objects[name] = schema;
    }
  }

  final ctx = _Ctx(enums: enums.keys.toSet(), objects: objects.keys.toSet());

  final b = StringBuffer()
    ..writeln('// GENERATED FILE — DO NOT EDIT BY HAND.')
    ..writeln('//')
    ..writeln('// Source of truth: the backend OpenAPI schema.')
    ..writeln('// Regenerate with:  dart run tool/generate_api_models.dart')
    ..writeln('//')
    ..writeln('// Doc comments below are the backend\'s own field descriptions. If one')
    ..writeln('// reads wrong, fix it in the Python schema, not here.')
    ..writeln('//')
    ..writeln('// ignore_for_file: unnecessary_cast, prefer_single_quotes')
    ..writeln();

  b
    ..writeln('/// A JSON value did not match the shape the schema promised.')
    ..writeln('///')
    ..writeln('/// Thrown rather than defaulted. A dose status or risk level that this')
    ..writeln('/// client does not recognise is a version mismatch with the backend, and')
    ..writeln('/// quietly substituting a fallback would show a patient or clinician a')
    ..writeln('/// value the server never sent.')
    ..writeln('class ApiSchemaMismatch implements Exception {')
    ..writeln('  ApiSchemaMismatch(this.message);')
    ..writeln()
    ..writeln('  final String message;')
    ..writeln()
    ..writeln('  @override')
    ..writeln('  String toString() => \'ApiSchemaMismatch: \$message\';')
    ..writeln('}')
    ..writeln()
    ..writeln('/// Date-only fields are transported as YYYY-MM-DD, not as a full instant.')
    ..writeln('String _encodeDate(DateTime value) =>')
    ..writeln('    \'\${value.year.toString().padLeft(4, \'0\')}-\'')
    ..writeln('    \'\${value.month.toString().padLeft(2, \'0\')}-\'')
    ..writeln('    \'\${value.day.toString().padLeft(2, \'0\')}\';')
    ..writeln();

  for (final name in enums.keys) {
    b.writeln(_renderEnum(name, enums[name]!, schemas[name] as Map<String, dynamic>));
  }

  for (final name in objects.keys) {
    b.writeln(_renderClass(ctx, name, objects[name]!));
  }

  return b.toString();
}

class _Ctx {
  _Ctx({required this.enums, required this.objects});

  final Set<String> enums;
  final Set<String> objects;
}

Never _unsupported(String what) {
  throw UnsupportedError(
    'The model generator does not handle $what. Extend '
    'tool/generate_api_models.dart deliberately rather than letting it guess.',
  );
}

// ---------------------------------------------------------------------------
// Naming
// ---------------------------------------------------------------------------

/// `Body_login_api_v1_auth_login_post` -> `BodyLoginApiV1AuthLoginPost`.
String _className(String schemaName) {
  final parts = schemaName
      .split(RegExp(r'[^A-Za-z0-9]+'))
      .where((p) => p.isNotEmpty)
      .toList();
  if (parts.length == 1) return _upperFirst(parts.single);
  return parts.map((p) => _upperFirst(p.toLowerCase())).join();
}

/// `skip_reason_code` -> `skipReasonCode`.
String _fieldName(String jsonKey) {
  final parts = jsonKey.split('_').where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) _unsupported('an empty property name');
  final head = parts.first;
  final tail = parts.skip(1).map(_upperFirst).join();
  final name = '$head$tail';
  return _dartKeywords.contains(name) ? '${name}Value' : name;
}

String _upperFirst(String s) =>
    s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

const _dartKeywords = {
  'default', 'class', 'is', 'in', 'new', 'const', 'final', 'var', 'this',
  'switch', 'case', 'for', 'while', 'return', 'void', 'null', 'true', 'false',
  'enum', 'extends', 'super', 'with', 'do', 'if', 'else', 'try', 'catch',
};

/// `CLINICIAN_INSTRUCTED` -> `clinicianInstructed`.
String _enumMemberName(String wire) {
  final parts = wire
      .split(RegExp(r'[^A-Za-z0-9]+'))
      .where((p) => p.isNotEmpty)
      .map((p) => p.toLowerCase())
      .toList();
  if (parts.isEmpty) _unsupported('an enum value with no usable characters');
  final name = parts.first + parts.skip(1).map(_upperFirst).join();
  final safe = RegExp(r'^[0-9]').hasMatch(name) ? 'v$name' : name;
  return _dartKeywords.contains(safe) ? '${safe}Value' : safe;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// A resolved Dart type plus how to move it across the JSON boundary.
class _Type {
  _Type({
    required this.name,
    required this.decode,
    required this.encode,
    this.nullable = false,
  });

  /// Dart type without the `?`.
  final String name;

  /// Given an expression of type `dynamic`, produce a typed one.
  final String Function(String src) decode;

  /// Given a typed expression, produce a JSON-safe one.
  final String Function(String src) encode;

  final bool nullable;

  _Type asNullable() =>
      _Type(name: name, decode: decode, encode: encode, nullable: true);
}

_Type _resolve(_Ctx ctx, Map<String, dynamic> schema, String where) {
  final ref = schema[r'$ref'] as String?;
  if (ref != null) return _resolveRef(ctx, ref, where);

  if (schema['anyOf'] is List) {
    final branches = (schema['anyOf'] as List).cast<Map<String, dynamic>>();
    final concrete =
        branches.where((b) => b['type'] != 'null').toList(growable: false);
    final nullable = concrete.length != branches.length;

    if (concrete.isEmpty) _unsupported('an anyOf with only null at $where');
    if (concrete.length > 1) {
      // e.g. ValidationError.loc items are string|integer. There is no useful
      // Dart union, and this only appears in FastAPI's own error envelope.
      final t = _dynamicType();
      return nullable ? t.asNullable() : t;
    }
    final t = _resolve(ctx, concrete.single, where);
    return nullable ? t.asNullable() : t;
  }

  if (schema['enum'] is List) {
    // An inline (unnamed) enum. Carry the underlying type; the closed vocabulary
    // is still enforced server-side.
    return _primitive(schema, where);
  }

  final type = schema['type'];
  if (type == 'array') {
    final items = schema['items'] as Map<String, dynamic>?;
    if (items == null) _unsupported('an array without items at $where');
    final inner = _resolve(ctx, items, '$where[]');
    final innerName = inner.nullable ? '${inner.name}?' : inner.name;
    return _Type(
      name: 'List<$innerName>',
      decode: (src) {
        final element = _decodeMaybeNull(inner, 'e');
        // A list of `dynamic` needs no per-element work; `.map((e) => e)` is a lint.
        return element == 'e'
            ? '($src as List<dynamic>).toList()'
            : '($src as List<dynamic>).map((e) => $element).toList()';
      },
      encode: (src) {
        final element = _encodeMaybeNull(inner, 'e');
        return element == 'e' ? src : '$src.map((e) => $element).toList()';
      },
    );
  }

  if (type == 'object') {
    final ap = schema['additionalProperties'];
    if (ap is Map<String, dynamic>) {
      final inner = _resolve(ctx, ap, '$where{}');
      final innerName = inner.nullable ? '${inner.name}?' : inner.name;
      return _Type(
        name: 'Map<String, $innerName>',
        decode: (src) => '($src as Map<String, dynamic>)'
            '.map((k, e) => MapEntry(k, ${_decodeMaybeNull(inner, 'e')}))',
        encode: (src) =>
            '$src.map((k, e) => MapEntry(k, ${_encodeMaybeNull(inner, 'e')}))',
      );
    }
    return _Type(
      name: 'Map<String, dynamic>',
      decode: (src) => '$src as Map<String, dynamic>',
      encode: (src) => src,
    );
  }

  if (type == null) return _dynamicType();

  return _primitive(schema, where);
}

_Type _resolveRef(_Ctx ctx, String ref, String where) {
  const prefix = '#/components/schemas/';
  if (!ref.startsWith(prefix)) _unsupported('the external \$ref "$ref" at $where');
  final schemaName = ref.substring(prefix.length);
  final dart = _className(schemaName);

  if (ctx.enums.contains(schemaName)) {
    return _Type(
      name: dart,
      decode: (src) => '$dart.fromWire($src as String)',
      encode: (src) => '$src.wire',
    );
  }
  if (ctx.objects.contains(schemaName)) {
    return _Type(
      name: dart,
      decode: (src) => '$dart.fromJson($src as Map<String, dynamic>)',
      encode: (src) => '$src.toJson()',
    );
  }
  _unsupported('a \$ref to unknown schema "$schemaName" at $where');
}

_Type _dynamicType() => _Type(
      name: 'dynamic',
      decode: (src) => src,
      encode: (src) => src,
    );

_Type _primitive(Map<String, dynamic> schema, String where) {
  final type = schema['type'] as String?;
  final format = schema['format'] as String?;

  switch (type) {
    case 'string':
      if (format == 'date-time') {
        return _Type(
          name: 'DateTime',
          decode: (src) => 'DateTime.parse($src as String)',
          encode: (src) => '$src.toIso8601String()',
        );
      }
      if (format == 'date') {
        return _Type(
          name: 'DateTime',
          decode: (src) => 'DateTime.parse($src as String)',
          encode: (src) => '_encodeDate($src)',
        );
      }
      // password / email / binary are all just strings on the wire.
      return _Type(
        name: 'String',
        decode: (src) => '$src as String',
        encode: (src) => src,
      );
    case 'integer':
      return _Type(
        name: 'int',
        decode: (src) => '($src as num).toInt()',
        encode: (src) => src,
      );
    case 'number':
      return _Type(
        name: 'double',
        decode: (src) => '($src as num).toDouble()',
        encode: (src) => src,
      );
    case 'boolean':
      return _Type(
        name: 'bool',
        decode: (src) => '$src as bool',
        encode: (src) => src,
      );
  }
  _unsupported('the type "$type" (format "$format") at $where');
}

String _decodeMaybeNull(_Type t, String src) =>
    t.nullable ? '$src == null ? null : ${t.decode(src)}' : t.decode(src);

String _encodeMaybeNull(_Type t, String src) =>
    t.nullable ? '$src == null ? null : ${t.encode(src)}' : t.encode(src);

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

String _renderEnum(String schemaName, List<String> values, Map<String, dynamic> schema) {
  final cls = _className(schemaName);
  final b = StringBuffer();

  b.write(_docComment(schema['description'] as String?, indent: ''));
  b.writeln('enum $cls {');
  for (final v in values) {
    b.writeln("  ${_enumMemberName(v)}('$v'),");
  }
  b
    ..writeln('  ;')
    ..writeln()
    ..writeln('  const $cls(this.wire);')
    ..writeln()
    ..writeln('  /// The exact string the backend sends and expects.')
    ..writeln('  final String wire;')
    ..writeln()
    ..writeln('  static $cls fromWire(String wire) => values.firstWhere(')
    ..writeln('        (v) => v.wire == wire,')
    ..writeln('        orElse: () => throw ApiSchemaMismatch(')
    ..writeln("            'Unknown $cls \"\$wire\" — this client is older than the backend'),")
    ..writeln('      );')
    ..writeln('}');
  return b.toString();
}

class _Field {
  _Field({
    required this.jsonKey,
    required this.dartName,
    required this.type,
    required this.nullable,
    required this.defaultLiteral,
    required this.description,
  });

  final String jsonKey;
  final String dartName;
  final _Type type;
  final bool nullable;

  /// Dart literal for the schema's `default`, or null if it has none.
  final String? defaultLiteral;
  final String? description;

  /// `dynamic` is already nullable; a `?` on it is a lint.
  String get declaredType =>
      (nullable && type.name != 'dynamic') ? '${type.name}?' : type.name;

  /// Required in the constructor when there is no default to fall back on.
  bool get isRequired => defaultLiteral == null && !nullable;
}

String _renderClass(_Ctx ctx, String schemaName, Map<String, dynamic> schema) {
  final cls = _className(schemaName);
  final props = (schema['properties'] as Map<String, dynamic>?) ?? const {};
  final required = ((schema['required'] as List?) ?? const []).cast<String>().toSet();

  final fields = <_Field>[];
  for (final key in props.keys) {
    final ps = props[key] as Map<String, dynamic>;
    final type = _resolve(ctx, ps, '$schemaName.$key');
    final hasDefault = ps.containsKey('default');

    // Nullable when the schema says so, or when the server may simply omit it.
    final nullable = type.nullable || (!required.contains(key) && !hasDefault);

    fields.add(
      _Field(
        jsonKey: key,
        dartName: _fieldName(key),
        type: type,
        nullable: nullable,
        defaultLiteral: hasDefault ? _literal(ctx, ps, ps['default']) : null,
        description: ps['description'] as String?,
      ),
    );
  }

  // Constructor params without defaults must come first for readability; Dart
  // named params have no ordering constraint, so sort for a stable, tidy output.
  final ordered = [...fields]..sort((a, b) {
        if (a.isRequired != b.isRequired) return a.isRequired ? -1 : 1;
        return 0;
      });

  final b = StringBuffer();
  b.write(_docComment(schema['description'] as String?, indent: ''));
  b.writeln('class $cls {');

  // Constructor
  if (fields.isEmpty) {
    b.writeln('  const $cls();');
  } else {
    b.writeln('  const $cls({');
    for (final f in ordered) {
      if (f.isRequired) {
        b.writeln('    required this.${f.dartName},');
      } else if (f.defaultLiteral != null) {
        b.writeln('    this.${f.dartName} = ${f.defaultLiteral},');
      } else {
        b.writeln('    this.${f.dartName},');
      }
    }
    b.writeln('  });');
  }
  b.writeln();

  // fromJson
  b.writeln('  factory $cls.fromJson(Map<String, dynamic> json) => $cls(');
  for (final f in fields) {
    final raw = "json['${f.jsonKey}']";
    final decoded = f.type.decode(raw);
    final isIdentity = decoded == raw;
    if (f.nullable) {
      // A `dynamic` field decodes to itself, so the null check is dead weight.
      b.writeln(
        isIdentity
            ? '        ${f.dartName}: $raw,'
            : '        ${f.dartName}: $raw == null ? null : $decoded,',
      );
    } else if (f.defaultLiteral != null) {
      // Absent means "server left it at the documented default".
      b.writeln(
        isIdentity
            ? '        ${f.dartName}: $raw ?? ${f.defaultLiteral},'
            : '        ${f.dartName}: $raw == null ? ${f.defaultLiteral} : $decoded,',
      );
    } else {
      b.writeln('        ${f.dartName}: $decoded,');
    }
  }
  b
    ..writeln('      );')
    ..writeln();

  // Fields
  for (final f in fields) {
    b.write(_docComment(f.description, indent: '  '));
    b.writeln('  final ${f.declaredType} ${f.dartName};');
    b.writeln();
  }

  // toJson. Nulls are omitted rather than sent: for a PATCH-style body an
  // explicit null means "clear this", which is not what an untouched field means.
  b.writeln('  Map<String, dynamic> toJson() {');
  b.writeln('    final json = <String, dynamic>{};');
  for (final f in fields) {
    if (f.nullable) {
      // Copied to a local so flow analysis promotes it. A public final field is
      // not promoted (a subclass could override the getter), and an inline
      // `x as DateTime.toIso8601String()` parses as a cast to a type, not a call.
      b
        ..writeln('    {')
        ..writeln('      final value = ${f.dartName};')
        ..writeln('      if (value != null) {')
        ..writeln("        json['${f.jsonKey}'] = ${f.type.encode('value')};")
        ..writeln('      }')
        ..writeln('    }');
    } else {
      b.writeln("    json['${f.jsonKey}'] = ${f.type.encode(f.dartName)};");
    }
  }
  b
    ..writeln('    return json;')
    ..writeln('  }')
    ..writeln('}');

  return b.toString();
}

/// Dart literal for a schema `default` value.
String _literal(_Ctx ctx, Map<String, dynamic> propSchema, Object? value) {
  if (value == null) return 'null';
  if (value is bool || value is num) return value.toString();
  if (value is List) {
    if (value.isEmpty) return 'const []';
    _unsupported('a non-empty list default ($value)');
  }
  if (value is String) {
    // An enum-typed field's default is its wire string; render the member.
    final ref = propSchema[r'$ref'] as String? ??
        ((propSchema['anyOf'] as List?)
                ?.cast<Map<String, dynamic>>()
                .firstWhere((b) => b.containsKey(r'$ref'), orElse: () => const {})[r'$ref']
            as String?);
    if (ref != null) {
      const prefix = '#/components/schemas/';
      final schemaName = ref.substring(prefix.length);
      if (ctx.enums.contains(schemaName)) {
        return '${_className(schemaName)}.${_enumMemberName(value)}';
      }
    }
    return "'${value.replaceAll(r'\', r'\\').replaceAll("'", r"\'")}'";
  }
  _unsupported('a default of type ${value.runtimeType}');
}

/// The backend's description, rendered as `///` lines.
String _docComment(String? text, {required String indent}) {
  if (text == null || text.trim().isEmpty) return '';
  final b = StringBuffer();
  for (final line in text.trimRight().split('\n')) {
    final trimmed = line.trimRight();
    b.writeln(trimmed.isEmpty ? '$indent///' : '$indent/// $trimmed');
  }
  return b.toString();
}
