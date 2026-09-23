import React, { useState, useEffect, useCallback, useRef } from "react";

// ---------------------------------------------------------------------------
// BhuRakshak AI — Citizen Hazard Reporting
// Covers: report form, GPS capture w/ manual fallback, submission to a mock
// backend (persistent via window.storage), admin recent-reports view,
// validation, and two seeded demo reports.
// ---------------------------------------------------------------------------

const FONT_IMPORT_ID = "bhurakshak-fonts";

function useFonts() {
  useEffect(() => {
    if (document.getElementById(FONT_IMPORT_ID)) return;
    const link = document.createElement("link");
    link.id = FONT_IMPORT_ID;
    link.rel = "stylesheet";
    link.href =
      "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap";
    document.head.appendChild(link);
  }, []);
}

const SEVERITY = {
  low: { label: "Low", color: "#4C7A5E", bg: "#E4EBDF" },
  medium: { label: "Medium", color: "#B4711F", bg: "#F2E3CC" },
  high: { label: "High", color: "#A63A2E", bg: "#F2DAD4" },
};

const HAZARD_TYPES = [
  "Road crack",
  "Debris / rockfall",
  "Slope movement",
  "Flooding",
  "Structural damage",
  "Other",
];

const DEMO_REPORTS = [
  {
    id: "demo-001",
    reporterName: "Aman Verma",
    district: "Nainital, Uttarakhand",
    hazardType: "Road crack",
    severity: "medium",
    description:
      "Long lateral crack across the hill-road surface near km marker 14, widened noticeably after last night's rain. No traffic control in place yet.",
    lat: 29.3919,
    lng: 79.4542,
    locationMethod: "gps",
    image: null,
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(),
    status: "success",
  },
  {
    id: "demo-002",
    reporterName: "Sunita Rawat",
    district: "Rudraprayag, Uttarakhand",
    hazardType: "Debris / rockfall",
    severity: "high",
    description:
      "Fresh rockfall blocking roughly half the carriageway below the ridge. Loose material still visible above the slope, possible further fall.",
    lat: 30.2849,
    lng: 78.9814,
    locationMethod: "manual",
    image: null,
    createdAt: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    status: "success",
  },
];

const MAX_IMAGE_BYTES = 2 * 1024 * 1024; // 2MB
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

function genId() {
  return "r-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 7);
}

function fmtCoord(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toFixed(5);
}

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error("Could not read file"));
    r.readAsDataURL(file);
  });
}

// ---------------------------------------------------------------------------

export default function App() {
  useFonts();
  const [tab, setTab] = useState("report");

  return (
    <div style={styles.appShell}>
      <TopBar tab={tab} setTab={setTab} />
      <div style={styles.contourBand} aria-hidden="true">
        <ContourLines />
      </div>
      <main style={styles.main}>
        {tab === "report" ? <ReportForm onSubmitted={() => setTab("report")} /> : <Dashboard />}
      </main>
      <Footer />
    </div>
  );
}

function TopBar({ tab, setTab }) {
  return (
    <header style={styles.topBar}>
      <div style={styles.brandBlock}>
        <div style={styles.brandMark}>भ</div>
        <div>
          <div style={styles.brandName}>BHURAKSHAK AI</div>
          <div style={styles.brandSub}>Citizen Hazard Reporting · SIH26001</div>
        </div>
      </div>
      <nav style={styles.tabRow}>
        <button
          onClick={() => setTab("report")}
          style={{ ...styles.tabBtn, ...(tab === "report" ? styles.tabBtnActive : {}) }}
        >
          Report a hazard
        </button>
        <button
          onClick={() => setTab("dashboard")}
          style={{ ...styles.tabBtn, ...(tab === "dashboard" ? styles.tabBtnActive : {}) }}
        >
          Command dashboard
        </button>
      </nav>
    </header>
  );
}

function ContourLines() {
  const lines = [10, 40, 70, 100, 130, 160];
  return (
    <svg viewBox="0 0 1200 120" width="100%" height="100%" preserveAspectRatio="none">
      {lines.map((y, i) => (
        <path
          key={i}
          d={`M0 ${y} C 200 ${y - 22}, 400 ${y + 22}, 600 ${y} S 1000 ${y - 18}, 1200 ${y}`}
          fill="none"
          stroke="#C9C2AA"
          strokeWidth="1"
          opacity={0.5 - i * 0.06}
        />
      ))}
    </svg>
  );
}

function Footer() {
  return (
    <footer style={styles.footer}>
      <span>Working MVP for demo · finish the critical path first</span>
      <span style={{ opacity: 0.6 }}>Priyanshu · 24BTCSE0085</span>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// REPORT FORM
// ---------------------------------------------------------------------------

const emptyForm = {
  reporterName: "",
  district: "",
  hazardType: HAZARD_TYPES[0],
  severity: "medium",
  description: "",
  lat: "",
  lng: "",
};

function ReportForm() {
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState({});
  const [locationMethod, setLocationMethod] = useState(null); // 'gps' | 'manual' | null
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [image, setImage] = useState(null); // {name, dataUrl, size}
  const [imageError, setImageError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitState, setSubmitState] = useState(null); // 'success' | 'error' | null
  const fileInputRef = useRef(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const requestGps = useCallback(() => {
    setLocationError("");
    if (!("geolocation" in navigator)) {
      setLocationError("Geolocation isn't available on this device. Enter coordinates manually.");
      setLocationMethod("manual");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({
          ...f,
          lat: pos.coords.latitude.toFixed(6),
          lng: pos.coords.longitude.toFixed(6),
        }));
        setLocationMethod("gps");
        setLocating(false);
      },
      (err) => {
        setLocating(false);
        setLocationMethod("manual");
        setLocationError(
          err.code === err.PERMISSION_DENIED
            ? "Location permission denied. Enter coordinates manually below."
            : "Couldn't get your location. Enter coordinates manually below."
        );
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
    );
  }, []);

  const handleImagePick = async (e) => {
    const file = e.target.files && e.target.files[0];
    setImageError("");
    if (!file) return;
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setImageError("Use a JPEG, PNG, or WEBP image.");
      setImage(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError("Image is too large. Keep it under 2MB.");
      setImage(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    try {
      const dataUrl = await fileToDataUrl(file);
      setImage({ name: file.name, dataUrl, size: file.size });
    } catch {
      setImageError("Couldn't read that image. Try another file.");
    }
  };

  const removeImage = () => {
    setImage(null);
    setImageError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const validate = () => {
    const e = {};
    if (!form.reporterName.trim()) e.reporterName = "Required.";
    if (!form.district.trim()) e.district = "Required.";
    if (!form.description.trim() || form.description.trim().length < 10)
      e.description = "Describe what you saw in at least 10 characters.";
    const lat = parseFloat(form.lat);
    const lng = parseFloat(form.lng);
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      e.location = "Capture GPS location or enter coordinates manually.";
    } else if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      e.location = "Coordinates look out of range. Check the values.";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const resetForm = () => {
    setForm(emptyForm);
    setImage(null);
    setLocationMethod(null);
    setLocationError("");
    setImageError("");
    setErrors({});
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitState(null);
    if (!validate()) return;

    setSubmitting(true);
    const report = {
      id: genId(),
      reporterName: form.reporterName.trim(),
      district: form.district.trim(),
      hazardType: form.hazardType,
      severity: form.severity,
      description: form.description.trim(),
      lat: parseFloat(form.lat),
      lng: parseFloat(form.lng),
      locationMethod: locationMethod || "manual",
      image: image ? image.dataUrl : null,
      createdAt: new Date().toISOString(),
      status: "success",
    };

    try {
      if (window.storage && typeof window.storage.set === "function") {
        const result = await window.storage.set(`reports:${report.id}`, JSON.stringify(report), true);
        if (!result) throw new Error("Storage write failed");
      }
      setSubmitState("success");
      resetForm();
    } catch (err) {
      setSubmitState("error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={styles.pageGrid}>
      <section style={styles.formCard}>
        <div style={styles.cardHeader}>
          <h1 style={styles.h1}>Report a hazard</h1>
          <p style={styles.subtext}>
            Cracks, debris, or slope movement — a few details and a pin on the map help the response
            team act fast.
          </p>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div style={styles.formGrid}>
            <Field label="Your name" error={errors.reporterName}>
              <input
                style={styles.input}
                value={form.reporterName}
                onChange={set("reporterName")}
                placeholder="Full name"
              />
            </Field>

            <Field label="District / location" error={errors.district}>
              <input
                style={styles.input}
                value={form.district}
                onChange={set("district")}
                placeholder="e.g. Nainital, Uttarakhand"
              />
            </Field>

            <Field label="Hazard type">
              <select style={styles.input} value={form.hazardType} onChange={set("hazardType")}>
                {HAZARD_TYPES.map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Severity">
              <div style={styles.severityRow}>
                {Object.entries(SEVERITY).map(([key, s]) => (
                  <button
                    type="button"
                    key={key}
                    onClick={() => setForm((f) => ({ ...f, severity: key }))}
                    style={{
                      ...styles.severityChip,
                      borderColor: form.severity === key ? s.color : "#C9C2AA",
                      background: form.severity === key ? s.bg : "transparent",
                      color: form.severity === key ? s.color : "#5C6455",
                    }}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </Field>

            <Field label="Description" error={errors.description} full>
              <textarea
                style={{ ...styles.input, minHeight: 96, resize: "vertical" }}
                value={form.description}
                onChange={set("description")}
                placeholder="What did you see? Include size, extent, and anything nearby at risk."
              />
            </Field>

            <Field label="Location" error={errors.location} full>
              <div style={styles.locationBlock}>
                <div style={styles.locationRow}>
                  <button type="button" onClick={requestGps} style={styles.gpsBtn} disabled={locating}>
                    {locating ? "Locating…" : "Use my current location"}
                  </button>
                  {locationMethod && (
                    <span style={styles.locationTag}>
                      {locationMethod === "gps" ? "GPS captured" : "Manual entry"}
                    </span>
                  )}
                </div>
                {locationError && <div style={styles.warnText}>{locationError}</div>}
                <div style={styles.coordRow}>
                  <input
                    style={{ ...styles.input, ...styles.mono }}
                    value={form.lat}
                    onChange={(e) => {
                      set("lat")(e);
                      setLocationMethod("manual");
                    }}
                    placeholder="Latitude"
                    inputMode="decimal"
                  />
                  <input
                    style={{ ...styles.input, ...styles.mono }}
                    value={form.lng}
                    onChange={(e) => {
                      set("lng")(e);
                      setLocationMethod("manual");
                    }}
                    placeholder="Longitude"
                    inputMode="decimal"
                  />
                </div>
              </div>
            </Field>

            <Field label="Photo (optional)" error={imageError} full>
              {!image ? (
                <label style={styles.uploadBox}>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={handleImagePick}
                    style={{ display: "none" }}
                  />
                  <span>Add a photo</span>
                  <span style={styles.uploadHint}>JPEG, PNG or WEBP · up to 2MB</span>
                </label>
              ) : (
                <div style={styles.imagePreviewRow}>
                  <img src={image.dataUrl} alt="Selected evidence" style={styles.imagePreview} />
                  <div>
                    <div style={styles.imageName}>{image.name}</div>
                    <button type="button" onClick={removeImage} style={styles.linkBtn}>
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </Field>
          </div>

          <div style={styles.submitRow}>
            <button type="submit" style={styles.submitBtn} disabled={submitting}>
              {submitting ? "Submitting…" : "Submit report"}
            </button>
            {submitState === "success" && (
              <span style={styles.successMsg}>Report submitted. It's now visible on the command dashboard.</span>
            )}
            {submitState === "error" && (
              <span style={styles.errorMsg}>Couldn't submit — check your connection and try again.</span>
            )}
          </div>
        </form>
      </section>

      <aside style={styles.sideCard}>
        <div style={styles.sideLabel}>Workflow, for the demo PPT</div>
        <ol style={styles.workflowList}>
          <li>Citizen or field worker opens the report form on their phone.</li>
          <li>Location is captured via GPS, or entered manually if permission is denied.</li>
          <li>Report — with optional photo — is submitted to the backend.</li>
          <li>It appears immediately on the command dashboard's recent-reports list.</li>
        </ol>
        <div style={styles.sideDivider} />
        <div style={styles.sideLabel}>Definition of done</div>
        <ul style={styles.checklist}>
          <li>Works from a fresh app start</li>
          <li>No keys or passwords committed</li>
          <li>No fake "live" or "AI accuracy" claims</li>
          <li>Tested one normal case, one failure case</li>
        </ul>
      </aside>
    </div>
  );
}

function Field({ label, error, full, children }) {
  return (
    <div style={{ gridColumn: full ? "1 / -1" : "auto" }}>
      <label style={styles.label}>{label}</label>
      {children}
      {error && <div style={styles.errorText}>{error}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ADMIN DASHBOARD
// ---------------------------------------------------------------------------

function Dashboard() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [filter, setFilter] = useState("all");
  const seeded = useRef(false);

  const loadReports = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      if (!window.storage) throw new Error("Storage unavailable");
      const listing = await window.storage.list("reports:", true);
      let keys = (listing && listing.keys) || [];

      if (keys.length === 0 && !seeded.current) {
        seeded.current = true;
        for (const demo of DEMO_REPORTS) {
          try {
            await window.storage.set(`reports:${demo.id}`, JSON.stringify(demo), true);
          } catch {
            // ignore individual seed failures
          }
        }
        const relist = await window.storage.list("reports:", true);
        keys = (relist && relist.keys) || [];
      }

      const items = [];
      for (const k of keys) {
        try {
          const res = await window.storage.get(k, true);
          if (res && res.value) items.push(JSON.parse(res.value));
        } catch {
          // skip unreadable entries
        }
      }
      items.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
      setReports(items);
    } catch (err) {
      setLoadError("Couldn't load reports right now.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const filtered = filter === "all" ? reports : reports.filter((r) => r.severity === filter);

  return (
    <div style={styles.dashboardWrap}>
      <div style={styles.dashHeaderRow}>
        <div>
          <h1 style={styles.h1}>Command dashboard</h1>
          <p style={styles.subtext}>Recent reports, newest first.</p>
        </div>
        <button type="button" onClick={loadReports} style={styles.refreshBtn}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div style={styles.filterRow}>
        {["all", "low", "medium", "high"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              ...styles.filterChip,
              ...(filter === f ? styles.filterChipActive : {}),
            }}
          >
            {f === "all" ? "All" : SEVERITY[f].label}
          </button>
        ))}
        <span style={styles.countTag}>{filtered.length} report{filtered.length === 1 ? "" : "s"}</span>
      </div>

      {loadError && <div style={styles.warnText}>{loadError}</div>}

      {loading ? (
        <div style={styles.emptyState}>Loading reports…</div>
      ) : filtered.length === 0 ? (
        <div style={styles.emptyState}>No reports yet. Submit one from the report form.</div>
      ) : (
        <div style={styles.reportList}>
          {filtered.map((r) => (
            <ReportRow key={r.id} report={r} />
          ))}
        </div>
      )}
    </div>
  );
}

function ReportRow({ report }) {
  const sev = SEVERITY[report.severity] || SEVERITY.medium;
  return (
    <div style={styles.reportRow}>
      {report.image ? (
        <img src={report.image} alt="" style={styles.rowThumb} />
      ) : (
        <div style={styles.rowThumbPlaceholder}>No photo</div>
      )}
      <div style={styles.rowBody}>
        <div style={styles.rowTopLine}>
          <span style={{ ...styles.severityBadge, color: sev.color, background: sev.bg }}>
            {sev.label}
          </span>
          <span style={styles.rowHazard}>{report.hazardType}</span>
          <span style={styles.rowTime}>{fmtTime(report.createdAt)}</span>
        </div>
        <div style={styles.rowDistrict}>{report.district}</div>
        <div style={styles.rowDesc}>{report.description}</div>
        <div style={styles.rowMeta}>
          <span style={styles.mono}>
            {fmtCoord(report.lat)}, {fmtCoord(report.lng)}
          </span>
          <span style={styles.dot}>·</span>
          <span>{report.locationMethod === "gps" ? "GPS" : "Manual"}</span>
          <span style={styles.dot}>·</span>
          <span>{report.reporterName}</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// STYLES
// ---------------------------------------------------------------------------

const INK = "#1B211D";
const PAPER = "#ECE6D6";
const MUTED = "#6C6A57";
const LINE = "#C9C2AA";
const FIELD_GREEN = "#2F5233";
const CARD = "#F5F1E6";

const styles = {
  appShell: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    color: INK,
    background: PAPER,
    minHeight: "100%",
    display: "flex",
    flexDirection: "column",
  },
  topBar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 12,
    padding: "16px 20px",
    borderBottom: `1px solid ${LINE}`,
    background: PAPER,
  },
  brandBlock: { display: "flex", alignItems: "center", gap: 10 },
  brandMark: {
    width: 34,
    height: 34,
    borderRadius: 4,
    background: FIELD_GREEN,
    color: "#EFE9D8",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    fontSize: 16,
  },
  brandName: { fontWeight: 700, fontSize: 15, letterSpacing: 0.5 },
  brandSub: { fontSize: 12, color: MUTED, fontFamily: "'JetBrains Mono', monospace" },
  tabRow: { display: "flex", gap: 6, background: "#E2DBC7", padding: 4, borderRadius: 6 },
  tabBtn: {
    border: "none",
    background: "transparent",
    padding: "8px 14px",
    borderRadius: 4,
    fontFamily: "inherit",
    fontSize: 13,
    fontWeight: 600,
    color: MUTED,
    cursor: "pointer",
  },
  tabBtnActive: { background: INK, color: PAPER },
  contourBand: { height: 40, opacity: 0.7, borderBottom: `1px solid ${LINE}` },
  main: { flex: 1, padding: "24px 20px 48px", maxWidth: 1080, margin: "0 auto", width: "100%", boxSizing: "border-box" },
  footer: {
    display: "flex",
    justifyContent: "space-between",
    padding: "14px 20px",
    borderTop: `1px solid ${LINE}`,
    fontSize: 12,
    color: MUTED,
  },

  pageGrid: { display: "grid", gridTemplateColumns: "minmax(0,1fr) 260px", gap: 20, alignItems: "start" },
  formCard: { background: CARD, border: `1px solid ${LINE}`, borderRadius: 6, padding: 24 },
  cardHeader: { marginBottom: 18 },
  h1: { fontSize: 22, fontWeight: 700, margin: "0 0 4px" },
  subtext: { fontSize: 13.5, color: MUTED, margin: 0, maxWidth: 480, lineHeight: 1.5 },

  formGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px 16px" },
  label: { display: "block", fontSize: 12.5, fontWeight: 600, color: "#4A4A3D", marginBottom: 6 },
  input: {
    width: "100%",
    boxSizing: "border-box",
    border: `1px solid ${LINE}`,
    borderRadius: 4,
    padding: "10px 11px",
    fontSize: 14,
    fontFamily: "inherit",
    background: "#FDFBF5",
    color: INK,
  },
  mono: { fontFamily: "'JetBrains Mono', monospace", fontSize: 13.5 },

  severityRow: { display: "flex", gap: 8 },
  severityChip: {
    flex: 1,
    padding: "9px 8px",
    borderRadius: 4,
    border: "1px solid",
    fontFamily: "inherit",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },

  locationBlock: { display: "flex", flexDirection: "column", gap: 8 },
  locationRow: { display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" },
  gpsBtn: {
    border: `1px solid ${FIELD_GREEN}`,
    background: "transparent",
    color: FIELD_GREEN,
    borderRadius: 4,
    padding: "9px 14px",
    fontFamily: "inherit",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  locationTag: {
    fontSize: 12,
    fontFamily: "'JetBrains Mono', monospace",
    color: MUTED,
    background: "#E2DBC7",
    padding: "3px 8px",
    borderRadius: 3,
  },
  coordRow: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 },

  uploadBox: {
    display: "flex",
    flexDirection: "column",
    gap: 3,
    border: `1px dashed ${LINE}`,
    borderRadius: 4,
    padding: "16px 14px",
    cursor: "pointer",
    color: MUTED,
    fontSize: 13.5,
    background: "#FDFBF5",
  },
  uploadHint: { fontSize: 11.5, color: "#9B977E" },
  imagePreviewRow: { display: "flex", alignItems: "center", gap: 12 },
  imagePreview: { width: 64, height: 64, objectFit: "cover", borderRadius: 4, border: `1px solid ${LINE}` },
  imageName: { fontSize: 13, marginBottom: 4, wordBreak: "break-all" },
  linkBtn: {
    border: "none",
    background: "none",
    color: "#A63A2E",
    fontSize: 12.5,
    fontWeight: 600,
    cursor: "pointer",
    padding: 0,
  },

  submitRow: { display: "flex", alignItems: "center", gap: 14, marginTop: 20, flexWrap: "wrap" },
  submitBtn: {
    border: "none",
    background: FIELD_GREEN,
    color: "#F2EFE2",
    padding: "11px 22px",
    borderRadius: 4,
    fontFamily: "inherit",
    fontSize: 14,
    fontWeight: 700,
    cursor: "pointer",
  },
  successMsg: { color: "#3B6B44", fontSize: 13 },
  errorMsg: { color: "#A63A2E", fontSize: 13 },
  errorText: { color: "#A63A2E", fontSize: 12, marginTop: 4 },
  warnText: { color: "#B4711F", fontSize: 12.5 },

  sideCard: {
    background: "transparent",
    border: `1px solid ${LINE}`,
    borderRadius: 6,
    padding: 18,
    fontSize: 13,
    color: "#4A4A3D",
    position: "sticky",
    top: 12,
  },
  sideLabel: { fontSize: 11.5, fontWeight: 700, color: MUTED, marginBottom: 8, letterSpacing: 0.3 },
  workflowList: { margin: "0 0 6px", paddingLeft: 18, lineHeight: 1.6 },
  sideDivider: { height: 1, background: LINE, margin: "14px 0" },
  checklist: { margin: 0, paddingLeft: 18, lineHeight: 1.7 },

  dashboardWrap: { display: "flex", flexDirection: "column", gap: 16 },
  dashHeaderRow: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 },
  refreshBtn: {
    border: `1px solid ${LINE}`,
    background: CARD,
    borderRadius: 4,
    padding: "9px 16px",
    fontFamily: "inherit",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  filterRow: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  filterChip: {
    border: `1px solid ${LINE}`,
    background: "transparent",
    borderRadius: 20,
    padding: "6px 14px",
    fontFamily: "inherit",
    fontSize: 12.5,
    fontWeight: 600,
    color: MUTED,
    cursor: "pointer",
  },
  filterChipActive: { background: INK, color: PAPER, borderColor: INK },
  countTag: { marginLeft: "auto", fontSize: 12.5, color: MUTED, fontFamily: "'JetBrains Mono', monospace" },

  emptyState: {
    border: `1px dashed ${LINE}`,
    borderRadius: 6,
    padding: 32,
    textAlign: "center",
    color: MUTED,
    fontSize: 13.5,
  },
  reportList: { display: "flex", flexDirection: "column", gap: 10 },
  reportRow: {
    display: "flex",
    gap: 14,
    background: CARD,
    border: `1px solid ${LINE}`,
    borderRadius: 6,
    padding: 14,
  },
  rowThumb: { width: 76, height: 76, objectFit: "cover", borderRadius: 4, flexShrink: 0 },
  rowThumbPlaceholder: {
    width: 76,
    height: 76,
    flexShrink: 0,
    borderRadius: 4,
    border: `1px dashed ${LINE}`,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    color: "#9B977E",
    textAlign: "center",
  },
  rowBody: { flex: 1, minWidth: 0 },
  rowTopLine: { display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" },
  severityBadge: { fontSize: 11.5, fontWeight: 700, padding: "2px 8px", borderRadius: 3 },
  rowHazard: { fontSize: 13, fontWeight: 600 },
  rowTime: { fontSize: 12, color: MUTED, marginLeft: "auto", fontFamily: "'JetBrains Mono', monospace" },
  rowDistrict: { fontSize: 13, fontWeight: 600, color: "#3D3D30", marginBottom: 3 },
  rowDesc: { fontSize: 13, color: "#4A4A3D", lineHeight: 1.5, marginBottom: 6 },
  rowMeta: { fontSize: 11.5, color: MUTED, display: "flex", alignItems: "center", gap: 6 },
  dot: { opacity: 0.6 },
};
