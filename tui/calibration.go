// Calibration status badge — PC-059 (#101) + PC-061 (#113).
//
// On startup the TUI fetches /v1/calibration/status from the proxy and
// renders a compact badge next to the Pipeline pane title so users
// immediately see whether the loaded model has supported Lens artifacts
// and whether an ASA control vector is in play. Verdict comes from the
// proxy's CalibrationStatus (proxy/calibration_status.go).
//
// Why the TUI does this: when a user swaps in a non-default GGUF, the
// lens silently no-ops and the agent loop still "works" — but without
// G(x) verification half the value of ATLAS is missing. The badge is
// the only visible signal that something is up.

package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type calibrationStatus struct {
	Lens struct {
		Verdict         string `json:"verdict"`
		CostFieldLoaded bool   `json:"cost_field_loaded"`
		CostFieldDim    int    `json:"cost_field_dim"`
		EmbedDim        int    `json:"embed_dim"`
		GxLoaded        bool   `json:"gx_loaded"`
		Hint            string `json:"hint"`
	} `json:"lens"`
	ASA struct {
		Verdict       string `json:"verdict"`
		VectorPath    string `json:"vector_path"`
		VectorPresent bool   `json:"vector_present"`
		Hint          string `json:"hint"`
	} `json:"asa"`
}

type calibrationStatusMsg struct {
	status *calibrationStatus
	err    error
}

// fetchCalibrationStatusCmd does an HTTP GET against the proxy. Fast — the
// proxy itself caches nothing here, but the upstream lens /health call is
// 3s-bounded and the rest is in-process. Total round-trip should be <4s.
// Fail-soft: on error we set status=nil and the badge falls back to a
// "not yet probed" placeholder rather than blocking startup.
func fetchCalibrationStatusCmd(proxyURL string) tea.Cmd {
	return func() tea.Msg {
		ctx, cancel := context.WithTimeout(context.Background(), 6*time.Second)
		defer cancel()
		req, err := http.NewRequestWithContext(ctx, "GET",
			strings.TrimRight(proxyURL, "/")+"/v1/calibration/status", nil)
		if err != nil {
			return calibrationStatusMsg{err: err}
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			return calibrationStatusMsg{err: err}
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			return calibrationStatusMsg{err: nil, status: nil}
		}
		var s calibrationStatus
		if err := json.NewDecoder(resp.Body).Decode(&s); err != nil {
			return calibrationStatusMsg{err: err}
		}
		return calibrationStatusMsg{status: &s}
	}
}

// Lipgloss styles for the three verdict states. Colors picked from the
// same palette as the rest of the TUI (panes.go's titleStyle reads from
// 117 / blue; we add green/yellow/red for verdict states).
var (
	badgeOK = lipgloss.NewStyle().
		Foreground(lipgloss.Color("78")). // green
		Bold(true)
	badgeWarn = lipgloss.NewStyle().
			Foreground(lipgloss.Color("214")). // amber
			Bold(true)
	badgeFail = lipgloss.NewStyle().
			Foreground(lipgloss.Color("203")). // red
			Bold(true)
	badgeDim = lipgloss.NewStyle().
			Foreground(lipgloss.Color("245")) // grey
)

// renderCalibrationBadge produces the compact badge text that gets
// appended to the Pipeline pane title.
//
//	"  Lens ✓  ASA ✓"   — both supported
//	"  Lens ⚠  ASA ⚠"   — at least one needs attention
//	"  cal …"            — fetch still in flight or failed
//
// Returns empty string when the badge should not be shown (e.g. the
// status fetch errored — better to omit than to render a confusing
// placeholder).
func renderCalibrationBadge(s *calibrationStatus) string {
	if s == nil {
		return badgeDim.Render("  cal …")
	}
	return "  " + renderOneBadge("Lens", s.Lens.Verdict) +
		"  " + renderOneBadge("ASA", s.ASA.Verdict)
}

func renderOneBadge(name, verdict string) string {
	switch verdict {
	case "supported":
		return badgeOK.Render(name+" ✓")
	case "no-artifacts", "missing", "dim-mismatch":
		return badgeWarn.Render(name+" ⚠")
	case "unreachable", "incompatible":
		return badgeFail.Render(name+" ✗")
	default:
		return badgeDim.Render(name + " ?")
	}
}

// calibrationTooltip renders the verbose hint text that the Stats pane
// surfaces below the pipeline (when the badge shows ⚠ or ✗). Currently
// emitted as a one-line summary; the full hint stays accessible via
// `atlas lens check` / `atlas asa check`.
func calibrationTooltip(s *calibrationStatus) string {
	if s == nil {
		return ""
	}
	var notes []string
	if s.Lens.Verdict != "supported" && s.Lens.Hint != "" {
		notes = append(notes, "Lens: "+s.Lens.Hint)
	}
	if s.ASA.Verdict != "supported" && s.ASA.Hint != "" {
		notes = append(notes, "ASA: "+s.ASA.Hint)
	}
	return strings.Join(notes, "  |  ")
}
