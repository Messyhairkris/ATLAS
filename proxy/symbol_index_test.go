package main

import (
	"reflect"
	"sort"
	"testing"
)

func TestExtractCandidateSymbols(t *testing.T) {
	cases := []struct {
		name string
		msg  string
		want []string
	}{
		{
			"backticked single ident",
			"please fix `dashboard`",
			[]string{"dashboard"},
		},
		{
			"the X function pattern",
			"the dashboard function is broken, fix it",
			[]string{"dashboard"},
		},
		{
			"the X class pattern",
			"make the UserModel class handle empty strings",
			[]string{"UserModel"},
		},
		{
			"dotted path expands to leaves",
			"add validation to UserModel.profile.email",
			[]string{"UserModel", "profile", "email"},
		},
		{
			"stopwords filtered",
			"fix the route the function the file",
			nil, // route, function, file all stopworded
		},
		{
			"mixed signals deduped",
			"fix `dashboard` — the dashboard function is broken",
			[]string{"dashboard"},
		},
		{
			"empty message",
			"",
			nil,
		},
		{
			"message with no symbols",
			"please clean up the formatting and add some comments",
			nil,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := extractCandidateSymbols(tc.msg)
			// Sort both for deterministic compare. Order doesn't matter
			// semantically — v3-service iterates regardless of order.
			gotSorted := append([]string{}, got...)
			wantSorted := append([]string{}, tc.want...)
			sort.Strings(gotSorted)
			sort.Strings(wantSorted)
			if len(gotSorted) == 0 && len(wantSorted) == 0 {
				return
			}
			if !reflect.DeepEqual(gotSorted, wantSorted) {
				t.Errorf("extractCandidateSymbols(%q) = %v, want %v", tc.msg, got, tc.want)
			}
		})
	}
}

func TestExtractCandidateSymbolsCap(t *testing.T) {
	// 12 backticked symbols — only the first symbolMaxCandidates (=10)
	// should be returned. Defends against a paste-bomb message that
	// would otherwise inflate the index lookup.
	msg := "look at `a1` `a2` `a3` `a4` `a5` `a6` `a7` `a8` `a9` `a10` `a11` `a12`"
	got := extractCandidateSymbols(msg)
	if len(got) != symbolMaxCandidates {
		t.Errorf("got %d symbols, want %d (cap)", len(got), symbolMaxCandidates)
	}
}
