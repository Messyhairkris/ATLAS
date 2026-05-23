// Tests for buildResponseFormat — the schema-constrained sampling path
// (#33). These tests pin the response_format payload shape that goes
// over the wire to llama-server, so a regression that silently flips
// the default back to loose JSON gets caught.

package main

import (
	"testing"
)

func TestBuildResponseFormat_DefaultIsStrictSchema(t *testing.T) {
	// Default mode (no env var set) must produce the schema-constrained
	// payload. This is the #33 perf optimization — losing the schema
	// means we silently regress to the wasted-token retry pattern.
	t.Setenv("ATLAS_GRAMMAR_MODE", "")
	rf := buildResponseFormat()

	m, ok := rf.(map[string]interface{})
	if !ok {
		t.Fatalf("strict mode should return map[string]interface{}, got %T", rf)
	}
	if m["type"] != "json_object" {
		t.Errorf("expected type=json_object, got %v", m["type"])
	}
	if _, has := m["schema"]; !has {
		t.Error("strict mode must include a 'schema' key — without it " +
			"llama-server falls back to plain valid-JSON-only enforcement " +
			"and the #33 optimization no-ops")
	}
}

func TestBuildResponseFormat_LooseDropsSchema(t *testing.T) {
	// Escape hatch: ATLAS_GRAMMAR_MODE=loose reverts to the pre-#33
	// "any valid JSON" behavior. Used when a model handles the schema
	// poorly or for debugging. The payload must NOT include 'schema'.
	t.Setenv("ATLAS_GRAMMAR_MODE", "loose")
	rf := buildResponseFormat()

	m, ok := rf.(map[string]string)
	if !ok {
		t.Fatalf("loose mode should return map[string]string, got %T", rf)
	}
	if m["type"] != "json_object" {
		t.Errorf("expected type=json_object, got %v", m["type"])
	}
}

func TestBuildResponseFormat_UnknownModeDefaultsToStrict(t *testing.T) {
	// Anything other than "loose" should fall through to strict.
	// Future modes (e.g. "json_schema" for the OpenAI-style payload)
	// would need explicit branches; until then unknown = strict, never
	// silently regress to loose.
	t.Setenv("ATLAS_GRAMMAR_MODE", "experimental-future-thing")
	rf := buildResponseFormat()
	m, ok := rf.(map[string]interface{})
	if !ok {
		t.Fatalf("unknown mode should still produce strict payload, "+
			"got %T (would silently lose the schema)", rf)
	}
	if _, has := m["schema"]; !has {
		t.Error("unknown mode must default to strict (schema included)")
	}
}

func TestBuildResponseFormat_SchemaMatchesToolRegistry(t *testing.T) {
	// The schema embedded in the response_format must match what
	// buildToolCallSchema() produces. If the two diverge, llama-server's
	// token sampler would constrain output to a stale set of tools and
	// the agent loop would reject responses from the model.
	t.Setenv("ATLAS_GRAMMAR_MODE", "strict")
	rf := buildResponseFormat()
	m := rf.(map[string]interface{})
	embedded, ok := m["schema"].(map[string]interface{})
	if !ok {
		t.Fatalf("schema field should be map[string]interface{}, got %T",
			m["schema"])
	}
	canonical := buildToolCallSchema()
	if len(embedded) != len(canonical) {
		t.Errorf("schema field has %d top-level keys, canonical has %d "+
			"— drift between buildResponseFormat and buildToolCallSchema",
			len(embedded), len(canonical))
	}
}
