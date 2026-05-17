// Calibration status endpoint — surfaces lens + ASA compat for the TUI.
//
// PC-059 (#101): the geometric-lens /health endpoint already exposes the
// data we need (cost_field_dim, embed_dim, cost_field_loaded). This file
// forwards that into a verdict-shaped response under /v1/calibration/status
// that the TUI renders as a header badge.
//
// PC-061 (#113) extends the `asa` block from a file-presence check to a
// proper dim-vs-model probe; the JSON shape stays the same so TUI
// rendering doesn't churn.

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

// CalibrationStatus is the JSON returned by /v1/calibration/status.
// Shape is stable: TUI and atlas doctor both key off it.
type CalibrationStatus struct {
	Lens LensStatus `json:"lens"`
	ASA  ASAStatus  `json:"asa"`
}

type LensStatus struct {
	// "supported" | "no-artifacts" | "dim-mismatch" | "unreachable"
	Verdict         string `json:"verdict"`
	CostFieldLoaded bool   `json:"cost_field_loaded"`
	CostFieldDim    int    `json:"cost_field_dim"`
	EmbedDim        int    `json:"embed_dim"`
	GxLoaded        bool   `json:"gx_loaded"`
	Hint            string `json:"hint"`
}

type ASAStatus struct {
	// "supported" | "missing" | "unverified"
	Verdict       string `json:"verdict"`
	VectorPath    string `json:"vector_path"`
	VectorPresent bool   `json:"vector_present"`
	Hint          string `json:"hint"`
}

// lensHealthShape mirrors the lens /health JSON we read. Defensive — the
// service can be reachable but mid-startup with partial fields. We treat
// missing fields as zero values rather than failing the whole probe.
type lensHealthShape struct {
	Status     string `json:"status"`
	Subsystems struct {
		Lens struct {
			Enabled         bool `json:"enabled"`
			CostFieldLoaded bool `json:"cost_field_loaded"`
			CostFieldDim    int  `json:"cost_field_dim"`
			EmbedDim        int  `json:"embed_dim"`
			GxLoaded        bool `json:"gx_loaded"`
			SelfTestPass    bool `json:"self_test_pass"`
		} `json:"lens"`
	} `json:"subsystems"`
}

// probeLensStatus calls the lens /health endpoint and renders a verdict.
// Timeout is short — this fires on a TUI startup ping and on the proxy's
// own startup banner; we don't want to block either if the lens is wedged.
func probeLensStatus(ctx context.Context, lensBaseURL string) LensStatus {
	out := LensStatus{Verdict: "unreachable",
		Hint: "geometric-lens unreachable at " + lensBaseURL +
			" (is the stack up?)"}

	pCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(pCtx, "GET", lensBaseURL+"/health", nil)
	if err != nil {
		return out
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return out
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return out
	}
	var h lensHealthShape
	if err := json.Unmarshal(body, &h); err != nil {
		out.Hint = "lens /health returned non-JSON: " + truncate(string(body), 80)
		return out
	}

	out.CostFieldLoaded = h.Subsystems.Lens.CostFieldLoaded
	out.CostFieldDim = h.Subsystems.Lens.CostFieldDim
	out.EmbedDim = h.Subsystems.Lens.EmbedDim
	out.GxLoaded = h.Subsystems.Lens.GxLoaded

	switch {
	case !out.CostFieldLoaded:
		out.Verdict = "no-artifacts"
		out.Hint = "no cost_field.pt loaded — run `atlas lens build` to train one"
	case out.EmbedDim > 0 && out.CostFieldDim != out.EmbedDim:
		out.Verdict = "dim-mismatch"
		out.Hint = fmt.Sprintf("cost_field expects %d-dim, model emits %d-dim "+
			"— run `atlas lens build` to retrain at the model's native dim",
			out.CostFieldDim, out.EmbedDim)
	default:
		out.Verdict = "supported"
		out.Hint = "ready"
	}
	return out
}

// probeASAStatus checks for the configured ASA control-vector file on disk.
// V3.1.1 first pass — only checks presence, not dim compatibility (PC-061
// extends to a full probe). The configured path lives on the llama-server
// container's filesystem, not the proxy's; this code path uses the env-var
// declaration ATLAS_CONTROL_VECTOR which both the proxy and entrypoint
// read identically, but the actual stat() lives in the llama-server image.
// For the proxy we fall back to the lens /health hint when we can't read
// the file directly.
func probeASAStatus() ASAStatus {
	path := envOr("ATLAS_CONTROL_VECTOR", "/models/ast_edit_steering.gguf")
	out := ASAStatus{VectorPath: path, Verdict: "unverified"}

	// Stat as a best-effort signal — the proxy may not share the same fs
	// view as llama-server, so a "not found" here doesn't always mean the
	// llama-server actually missed it. PC-061 will deepen this with a
	// dim+layers probe via the lens service.
	if _, err := os.Stat(path); err == nil {
		out.VectorPresent = true
		out.Verdict = "supported"
		out.Hint = "control vector present (dim-compat check is V3.1.2 work — see PC-061)"
	} else if os.IsNotExist(err) {
		out.VectorPresent = false
		out.Verdict = "missing"
		out.Hint = "no control vector at " + path +
			" — build one via `atlas asa build` (PC-061) " +
			"or geometric-lens/asa_calibration/README.md"
	} else {
		out.Hint = "stat(" + path + ") failed: " + err.Error()
	}
	return out
}

func handleCalibrationStatus(w http.ResponseWriter, r *http.Request) {
	status := CalibrationStatus{
		Lens: probeLensStatus(r.Context(), lensURL),
		ASA:  probeASAStatus(),
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(status)
}

// logCalibrationStatusAtStartup is called once from main() so operators
// see the same compat verdict the TUI will render, in the proxy banner.
// Fail-soft: if the lens service isn't reachable yet, we log it and move
// on — startup blocks long enough as-is without a synchronous probe.
func logCalibrationStatusAtStartup() {
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Second)
	defer cancel()
	lens := probeLensStatus(ctx, lensURL)
	asa := probeASAStatus()
	log.Printf("  Lens: %s — %s", lens.Verdict, lens.Hint)
	log.Printf("  ASA:  %s — %s", asa.Verdict, asa.Hint)
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
