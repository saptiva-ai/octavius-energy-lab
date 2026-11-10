#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

const DEFAULT_JSON_PATH = "test-results/results.json";
const DEFAULT_PDF_PATH = "test-results/e2e-report.pdf";
const MAX_ERROR_CHARS = 8_000;

function sanitizeText(raw) {
  const value = String(raw ?? "");
  return value
    .replace(/\u001b\[[0-9;?]*[ -/]*[@-~]/gi, "")
    .replace(/\u009b[0-9;?]*[ -/]*[@-~]/gi, "")
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "");
}

function parseArgs(argv) {
  const parsed = {
    jsonPath: DEFAULT_JSON_PATH,
    outputPath: DEFAULT_PDF_PATH,
    title: "Playwright E2E Test Report",
    testType: "suite",
    baseURL: "",
    runCommand: "",
    gitSha: "",
    jsonArchivePath: "",
    excludeProjects: ["setup"],
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--json" && argv[index + 1]) {
      parsed.jsonPath = argv[index + 1];
      index += 1;
    } else if (token === "--output" && argv[index + 1]) {
      parsed.outputPath = argv[index + 1];
      index += 1;
    } else if (token === "--title" && argv[index + 1]) {
      parsed.title = argv[index + 1];
      index += 1;
    } else if (token === "--test-type" && argv[index + 1]) {
      parsed.testType = argv[index + 1];
      index += 1;
    } else if (token === "--base-url" && argv[index + 1]) {
      parsed.baseURL = argv[index + 1];
      index += 1;
    } else if (token === "--run-command" && argv[index + 1]) {
      parsed.runCommand = argv[index + 1];
      index += 1;
    } else if (token === "--git-sha" && argv[index + 1]) {
      parsed.gitSha = argv[index + 1];
      index += 1;
    } else if (token === "--json-archive-path" && argv[index + 1]) {
      parsed.jsonArchivePath = argv[index + 1];
      index += 1;
    } else if (token === "--exclude-projects" && argv[index + 1]) {
      const rawProjects = String(argv[index + 1] || "");
      parsed.excludeProjects = rawProjects
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      index += 1;
    }
  }

  return parsed;
}

function escapeHtml(raw) {
  return sanitizeText(raw)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function truncateText(raw, maxLength = 600) {
  const value = sanitizeText(raw);
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
}

function guessContentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".webp") return "image/webp";
  if (ext === ".gif") return "image/gif";
  if (ext === ".webm") return "video/webm";
  if (ext === ".zip") return "application/zip";
  if (ext === ".json") return "application/json";
  return "application/octet-stream";
}

async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function resolveAttachmentPath(baseDir, rawPath) {
  if (!rawPath) return null;
  if (path.isAbsolute(rawPath)) return rawPath;
  return path.resolve(baseDir, rawPath);
}

function classifyAttachment(attachment) {
  const name = (attachment.name || "").toLowerCase();
  const contentType = (attachment.contentType || "").toLowerCase();
  const rawPath = attachment.path || "";
  const ext = path.extname(rawPath).toLowerCase();

  if (
    contentType.startsWith("image/") ||
    [".png", ".jpg", ".jpeg", ".webp"].includes(ext) ||
    name.includes("screenshot")
  ) {
    return "image";
  }

  if (
    contentType.startsWith("video/") ||
    ext === ".webm" ||
    name.includes("video")
  ) {
    return "video";
  }

  if (ext === ".zip" || name.includes("trace")) {
    return "trace";
  }

  if (contentType.includes("json") || ext === ".json") {
    if (
      name.includes("grounding") ||
      name.includes("expected") ||
      name.includes("actual") ||
      name.includes("mapping")
    ) {
      return "grounding";
    }
    return "json";
  }

  return "other";
}

function flattenSuites(suites, parentTitles = [], output = []) {
  for (const suite of suites ?? []) {
    const currentParents = suite.title
      ? [...parentTitles, suite.title]
      : [...parentTitles];

    for (const spec of suite.specs ?? []) {
      const titleParts = [...currentParents, spec.title].filter(Boolean);
      const fullTitle = titleParts.join(" > ");

      for (const test of spec.tests ?? []) {
        const results = Array.isArray(test.results) ? test.results : [];
        const finalResult = results.length ? results[results.length - 1] : {};
        const errors = [];

        if (Array.isArray(finalResult.errors)) {
          errors.push(...finalResult.errors);
        }
        if (finalResult.error) {
          errors.push(finalResult.error);
        }

        output.push({
          id: test.id || `${fullTitle}:${test.projectName || "default"}`,
          title: fullTitle,
          projectName: test.projectName || "default",
          status: finalResult.status || test.status || "unknown",
          duration: Number(finalResult.duration || 0),
          attachments: Array.isArray(finalResult.attachments)
            ? finalResult.attachments
            : [],
          errors,
        });
      }
    }

    flattenSuites(suite.suites, currentParents, output);
  }

  return output;
}

function filterEntriesByProject(entries, excludedProjects) {
  const excluded = new Set(
    (excludedProjects || [])
      .map((project) =>
        String(project || "")
          .toLowerCase()
          .trim(),
      )
      .filter(Boolean),
  );

  if (excluded.size === 0) {
    return {
      includedEntries: entries,
      excludedCount: 0,
      excludedProjects: [],
    };
  }

  const includedEntries = entries.filter((entry) => {
    const projectName = String(entry.projectName || "")
      .toLowerCase()
      .trim();
    return !excluded.has(projectName);
  });

  return {
    includedEntries,
    excludedCount: entries.length - includedEntries.length,
    excludedProjects: Array.from(excluded),
  };
}

function buildSummary(entries) {
  const summary = {
    total: entries.length,
    passed: 0,
    failed: 0,
    skipped: 0,
    timedOut: 0,
    interrupted: 0,
    unknown: 0,
  };

  for (const entry of entries) {
    const status = String(entry.status || "unknown");
    if (status === "passed") summary.passed += 1;
    else if (status === "failed") summary.failed += 1;
    else if (status === "skipped") summary.skipped += 1;
    else if (status === "timedOut") summary.timedOut += 1;
    else if (status === "interrupted") summary.interrupted += 1;
    else summary.unknown += 1;
  }

  return summary;
}

async function toImageDataUri(baseDir, attachment) {
  const contentType =
    attachment.contentType ||
    guessContentType(attachment.path || attachment.name || "image.png");

  if (attachment.body) {
    if (typeof attachment.body === "string") {
      return `data:${contentType};base64,${attachment.body}`;
    }
    if (Array.isArray(attachment.body)) {
      const base64 = Buffer.from(attachment.body).toString("base64");
      return `data:${contentType};base64,${base64}`;
    }
  }

  const resolvedPath = resolveAttachmentPath(baseDir, attachment.path);
  if (!resolvedPath || !(await fileExists(resolvedPath))) {
    return null;
  }

  const content = await fs.readFile(resolvedPath);
  const base64 = content.toString("base64");
  return `data:${contentType};base64,${base64}`;
}

function formatDurationMs(durationMs) {
  const milliseconds = Number(durationMs || 0);
  const seconds = milliseconds / 1000;
  if (seconds < 60) return `${seconds.toFixed(2)}s`;
  const minutes = Math.floor(seconds / 60);
  const remSeconds = seconds % 60;
  return `${minutes}m ${remSeconds.toFixed(1)}s`;
}

function toFileLink(baseDir, rawPath) {
  const resolvedPath = resolveAttachmentPath(baseDir, rawPath);
  if (!resolvedPath) return null;
  return {
    path: resolvedPath,
    href: pathToFileURL(resolvedPath).href,
  };
}

function errorToMessage(error) {
  if (!error) return "";
  if (typeof error === "string") return sanitizeText(error);
  if (typeof error.message === "string" && error.message.length > 0) {
    return sanitizeText(error.message);
  }
  if (typeof error.value === "string" && error.value.length > 0) {
    return sanitizeText(error.value);
  }
  return sanitizeText(JSON.stringify(error, null, 2));
}

function normalizeAttachmentText(rawBody) {
  if (!rawBody) return "";

  if (Array.isArray(rawBody)) {
    return Buffer.from(rawBody).toString("utf-8");
  }

  if (typeof rawBody !== "string") {
    return "";
  }

  const trimmed = rawBody.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    return rawBody;
  }

  try {
    const decoded = Buffer.from(rawBody, "base64").toString("utf-8");
    const decodedTrimmed = decoded.trim();
    if (decodedTrimmed.startsWith("{") || decodedTrimmed.startsWith("[")) {
      return decoded;
    }
  } catch {
    // Ignore base64 decode failures and fallback to raw string.
  }

  return rawBody;
}

async function parseGroundingAttachment(baseDir, attachment) {
  const candidates = [];
  if (attachment.body) {
    candidates.push(normalizeAttachmentText(attachment.body));
  }

  const resolvedPath = resolveAttachmentPath(baseDir, attachment.path);
  if (resolvedPath && (await fileExists(resolvedPath))) {
    candidates.push(await fs.readFile(resolvedPath, "utf-8"));
  }

  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "string") {
      continue;
    }

    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    } catch {
      // Continue trying other sources.
    }
  }

  return null;
}

function groundingStatusClass(matched) {
  if (matched === true) return "grounding-ok";
  if (matched === false) return "grounding-fail";
  return "grounding-unknown";
}

function groundingStatusText(matched) {
  if (matched === true) return "MATCH";
  if (matched === false) return "MISMATCH";
  return "UNKNOWN";
}

function formatComparisonValue(rawValue) {
  if (rawValue === null || rawValue === undefined) return "";
  if (typeof rawValue === "string" || typeof rawValue === "number") {
    return String(rawValue);
  }
  return JSON.stringify(rawValue);
}

function fieldLabel(fieldName) {
  const normalized = String(fieldName || "").toLowerCase();
  if (normalized === "period") return "Periodo";
  if (normalized === "value") return "Valor";
  if (normalized === "valuepattern") return "Valor esperado";
  if (normalized === "bankname") return "Banco";
  return fieldName;
}

function renderGroundingHtml(groundingDataList) {
  if (!Array.isArray(groundingDataList) || groundingDataList.length === 0) {
    return "";
  }

  const sections = groundingDataList
    .map((rawData, index) => {
      const expected =
        rawData && typeof rawData.expected === "object" ? rawData.expected : {};
      const actual =
        rawData && typeof rawData.actual === "object" ? rawData.actual : {};
      const rows = Array.isArray(rawData?.rows) ? rawData.rows.slice(0, 8) : [];
      const label =
        rawData?.label ||
        rawData?.metric ||
        rawData?.bankName ||
        `Grounding ${index + 1}`;
      const matched = rawData?.matched;
      const evidenceQuery =
        typeof rawData?.query === "string" && rawData.query.trim().length > 0
          ? rawData.query.trim()
          : "";

      const knownFields = ["period", "value", "valuePattern", "bankName"];
      const dynamicFields = [
        ...Object.keys(expected || {}),
        ...Object.keys(actual || {}),
      ].filter((field) => !knownFields.includes(field));
      const comparisonFields = Array.from(
        new Set([...knownFields, ...dynamicFields]),
      );

      const comparisonRows = comparisonFields
        .map((field) => {
          const expectedValue =
            expected?.[field] ??
            (field === "value" ? expected?.valuePattern : undefined) ??
            "";
          const actualValue = actual?.[field] ?? "";
          if (
            formatComparisonValue(expectedValue).length === 0 &&
            formatComparisonValue(actualValue).length === 0
          ) {
            return "";
          }
          return `
          <tr>
            <td>${escapeHtml(fieldLabel(field))}</td>
            <td>${escapeHtml(formatComparisonValue(expectedValue))}</td>
            <td>${escapeHtml(formatComparisonValue(actualValue))}</td>
          </tr>
        `;
        })
        .filter(Boolean)
        .map((row) => row)
        .join("");

      const rowsPreview = rows.length
        ? `
          <div class="grounding-preview">
            <p class="evidence-label">Table Snapshot (first ${rows.length} rows)</p>
            <table class="grounding-table">
              <thead>
                <tr>
                  <th>Banco</th>
                  <th>Periodo</th>
                  <th>Valor</th>
                </tr>
              </thead>
              <tbody>
                ${rows
                  .map(
                    (row) => `
                      <tr>
                        <td>${escapeHtml(row?.bank ?? row?.raw?.[0] ?? "")}</td>
                        <td>${escapeHtml(row?.period ?? row?.raw?.[1] ?? "")}</td>
                        <td>${escapeHtml(row?.value ?? row?.raw?.[2] ?? "")}</td>
                      </tr>
                    `,
                  )
                  .join("")}
              </tbody>
            </table>
          </div>
        `
        : "";

      return `
        <div class="grounding-block ${groundingStatusClass(matched)}">
          <div class="grounding-header">
            <p class="evidence-label">Grounding Check: ${escapeHtml(label)}</p>
            <span class="pill">${groundingStatusText(matched)}</span>
          </div>
          ${
            evidenceQuery
              ? `<p class="grounding-query"><strong>Query:</strong> ${escapeHtml(evidenceQuery)}</p>`
              : ""
          }
          <table class="grounding-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Expected</th>
                <th>Actual</th>
              </tr>
            </thead>
            <tbody>
              ${comparisonRows}
            </tbody>
          </table>
          ${rowsPreview}
        </div>
      `;
    })
    .join("");

  return `<div class="evidence-block">${sections}</div>`;
}

async function buildTestRowsHtml(baseDir, entries) {
  const rows = [];
  for (const entry of entries) {
    const imageAttachments = entry.attachments.filter(
      (attachment) => classifyAttachment(attachment) === "image",
    );
    const videoAttachments = entry.attachments.filter(
      (attachment) => classifyAttachment(attachment) === "video",
    );
    const traceAttachments = entry.attachments.filter(
      (attachment) => classifyAttachment(attachment) === "trace",
    );
    const jsonAttachments = entry.attachments.filter(
      (attachment) => classifyAttachment(attachment) === "json",
    );
    const groundingAttachments = entry.attachments.filter(
      (attachment) => classifyAttachment(attachment) === "grounding",
    );
    const otherAttachments = entry.attachments.filter(
      (attachment) => classifyAttachment(attachment) === "other",
    );

    const screenshotItems = [];
    for (const attachment of imageAttachments) {
      const screenshotDataUri = await toImageDataUri(baseDir, attachment);
      if (!screenshotDataUri) continue;
      const label =
        attachment.name || path.basename(attachment.path || "") || "screenshot";
      screenshotItems.push({
        dataUri: screenshotDataUri,
        label,
      });
    }

    const errorMessages = entry.errors
      .map((error) => truncateText(errorToMessage(error), MAX_ERROR_CHARS))
      .filter(Boolean);

    const groundingData = [];
    for (const attachment of groundingAttachments) {
      const parsed = await parseGroundingAttachment(baseDir, attachment);
      if (parsed) {
        groundingData.push(parsed);
      }
    }
    const groundingHtml = renderGroundingHtml(groundingData);

    const fileLinks = [
      ...videoAttachments.map((attachment) => ({
        type: "video",
        link: toFileLink(baseDir, attachment.path),
      })),
      ...traceAttachments.map((attachment) => ({
        type: "trace",
        link: toFileLink(baseDir, attachment.path),
      })),
      ...jsonAttachments.map((attachment) => ({
        type: "json",
        link: toFileLink(baseDir, attachment.path),
      })),
      ...otherAttachments.map((attachment) => ({
        type: "artifact",
        link: toFileLink(baseDir, attachment.path),
      })),
    ]
      .filter((item) => item.link)
      .map(
        (item) =>
          `<li><a href="${escapeHtml(item.link.href)}">${escapeHtml(
            `${item.type}: ${path.basename(item.link.path)}`,
          )}</a></li>`,
      )
      .join("");

    rows.push(`
      <section class="test-card status-${escapeHtml(entry.status)}">
        <div class="header">
          <h3>${escapeHtml(entry.title)}</h3>
          <span class="pill">${escapeHtml(entry.projectName)}</span>
        </div>
        <div class="meta">
          <span class="status">${escapeHtml(entry.status)}</span>
          <span>${escapeHtml(formatDurationMs(entry.duration))}</span>
          <span>attachments: ${entry.attachments.length}</span>
        </div>
        ${errorMessages
          .map(
            (errorMessage) =>
              `<pre class="error">${escapeHtml(errorMessage)}</pre>`,
          )
          .join("")}
        ${
          screenshotItems.length > 0
            ? `<div class="evidence-block">
                <p class="evidence-label">Screenshots (${screenshotItems.length})</p>
                <div class="screenshot-grid">
                  ${screenshotItems
                    .map(
                      (item) => `
                        <figure class="screenshot-item">
                          <figcaption>${escapeHtml(item.label)}</figcaption>
                          <img src="${item.dataUri}" alt="${escapeHtml(item.label)}" />
                        </figure>
                      `,
                    )
                    .join("")}
                </div>
              </div>`
            : ""
        }
        ${groundingHtml}
        ${
          fileLinks
            ? `<div class="evidence-block">
                <p class="evidence-label">Artifacts</p>
                <ul>${fileLinks}</ul>
              </div>`
            : ""
        }
      </section>
    `);
  }

  return rows.join("\n");
}

function buildGlobalErrorsHtml(globalErrors) {
  if (!Array.isArray(globalErrors) || globalErrors.length === 0) {
    return "";
  }

  const items = globalErrors
    .map((error) => truncateText(errorToMessage(error), MAX_ERROR_CHARS))
    .filter(Boolean)
    .map(
      (message) => `<li><pre class="error">${escapeHtml(message)}</pre></li>`,
    )
    .join("");

  return `
    <section class="global-errors">
      <h2>Global Runner Errors</h2>
      <ul>${items}</ul>
    </section>
  `;
}

function buildRunMetadataHtml(metadata) {
  const rows = [
    ["Test Type", metadata.testType],
    ["Base URL", metadata.baseURL],
    ["Git SHA", metadata.gitSha],
    ["Run Command", metadata.runCommand],
    ["Started At", metadata.startedAt],
    ["Duration", formatDurationMs(metadata.durationMs)],
    ["Expected", metadata.expected],
    ["Unexpected", metadata.unexpected],
    ["Flaky", metadata.flaky],
    ["Excluded Projects", metadata.excludedProjects],
    ["Excluded Tests", metadata.excludedCount],
    ["Workers", metadata.workers],
    ["Config File", metadata.configFile],
    ["JSON Source", metadata.jsonSourcePath],
    ["JSON Archive", metadata.jsonArchivePath],
  ];

  const htmlRows = rows
    .filter((row) => String(row[1] ?? "").length > 0)
    .map(
      (row) => `
        <tr>
          <th>${escapeHtml(row[0])}</th>
          <td>${escapeHtml(row[1])}</td>
        </tr>
      `,
    )
    .join("");

  if (!htmlRows) {
    return "";
  }

  return `
    <section class="run-metadata">
      <h2>Run Metadata</h2>
      <table>
        <tbody>${htmlRows}</tbody>
      </table>
    </section>
  `;
}

function buildHtmlDocument({
  title,
  generatedAt,
  summary,
  rowsHtml,
  globalErrorsHtml,
  runMetadataHtml,
}) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>${escapeHtml(title)}</title>
    <style>
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Segoe UI", Arial, sans-serif;
        color: #111827;
        background: #f3f4f6;
      }
      .container {
        max-width: 980px;
        margin: 0 auto;
        padding: 24px;
      }
      .cover {
        background: linear-gradient(135deg, #0f172a, #1e3a8a);
        color: #ffffff;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
      }
      .cover h1 {
        margin: 0 0 8px;
        font-size: 26px;
      }
      .cover p {
        margin: 0;
        font-size: 13px;
        opacity: 0.9;
      }
      .summary-grid {
        display: grid;
        grid-template-columns: repeat(7, minmax(0, 1fr));
        gap: 10px;
        margin: 18px 0 24px;
      }
      .summary-item {
        background: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 10px;
        padding: 12px;
      }
      .summary-item .label {
        font-size: 11px;
        color: #4b5563;
      }
      .summary-item .value {
        margin-top: 4px;
        font-size: 18px;
        font-weight: 700;
      }
      .run-metadata {
        margin: 6px 0 20px;
        padding: 12px;
        border: 1px solid #d1d5db;
        border-radius: 10px;
        background: #ffffff;
      }
      .run-metadata h2 {
        margin: 0 0 8px;
        font-size: 13px;
      }
      .run-metadata table {
        width: 100%;
        border-collapse: collapse;
      }
      .run-metadata th,
      .run-metadata td {
        font-size: 11px;
        border-top: 1px solid #e5e7eb;
        padding: 6px 8px;
        text-align: left;
        vertical-align: top;
      }
      .run-metadata th {
        width: 180px;
        color: #374151;
        font-weight: 700;
      }
      .global-errors {
        margin: 6px 0 20px;
        padding: 12px;
        border: 1px solid #fecaca;
        background: #fef2f2;
        border-radius: 10px;
      }
      .global-errors h2 {
        margin: 0 0 8px;
        font-size: 13px;
        color: #7f1d1d;
      }
      .global-errors ul {
        margin: 0;
        padding-left: 18px;
      }
      .tests {
        display: flex;
        flex-direction: column;
        gap: 14px;
      }
      .test-card {
        background: #ffffff;
        border: 1px solid #d1d5db;
        border-left-width: 6px;
        border-radius: 10px;
        padding: 14px;
        page-break-inside: avoid;
      }
      .status-passed { border-left-color: #16a34a; }
      .status-failed { border-left-color: #dc2626; }
      .status-skipped { border-left-color: #64748b; }
      .status-timedOut { border-left-color: #ea580c; }
      .status-interrupted { border-left-color: #9333ea; }
      .status-unknown { border-left-color: #0ea5e9; }
      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }
      .header h3 {
        margin: 0;
        font-size: 13px;
        line-height: 1.3;
      }
      .pill {
        border: 1px solid #cbd5e1;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 10px;
        white-space: nowrap;
      }
      .meta {
        display: flex;
        gap: 12px;
        margin-top: 8px;
        font-size: 11px;
        color: #4b5563;
      }
      .status {
        text-transform: uppercase;
        font-weight: 700;
      }
      .error {
        margin: 10px 0;
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 6px;
        padding: 8px;
        font-size: 10px;
        white-space: pre-wrap;
        color: #7f1d1d;
      }
      .evidence-block {
        margin-top: 10px;
      }
      .evidence-label {
        margin: 0 0 6px;
        font-size: 11px;
        color: #374151;
        font-weight: 600;
      }
      .grounding-block {
        margin-bottom: 10px;
        padding: 8px;
        border: 1px solid #d1d5db;
        border-radius: 8px;
      }
      .grounding-ok { border-color: #86efac; background: #f0fdf4; }
      .grounding-fail { border-color: #fecaca; background: #fef2f2; }
      .grounding-unknown { border-color: #d1d5db; background: #f8fafc; }
      .grounding-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
      }
      .grounding-query {
        margin: 8px 0;
        font-size: 10px;
        color: #1f2937;
      }
      .grounding-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 10px;
      }
      .grounding-table th,
      .grounding-table td {
        border: 1px solid #e5e7eb;
        padding: 4px 6px;
        text-align: left;
      }
      .grounding-preview {
        margin-top: 8px;
      }
      .screenshot-grid {
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .screenshot-item {
        margin: 0;
      }
      .screenshot-item figcaption {
        margin: 0 0 4px;
        font-size: 10px;
        color: #4b5563;
      }
      img {
        width: 100%;
        max-height: 360px;
        object-fit: contain;
        border: 1px solid #d1d5db;
        border-radius: 6px;
      }
      ul {
        margin: 0;
        padding-left: 18px;
      }
      li {
        margin: 2px 0;
        font-size: 11px;
      }
      a {
        color: #1d4ed8;
        text-decoration: none;
      }
      a:hover {
        text-decoration: underline;
      }
    </style>
  </head>
  <body>
    <main class="container">
      <section class="cover">
        <h1>${escapeHtml(title)}</h1>
        <p>Generated at ${escapeHtml(generatedAt)}</p>
      </section>

      <section class="summary-grid">
        <article class="summary-item">
          <div class="label">Total</div>
          <div class="value">${summary.total}</div>
        </article>
        <article class="summary-item">
          <div class="label">Passed</div>
          <div class="value">${summary.passed}</div>
        </article>
        <article class="summary-item">
          <div class="label">Failed</div>
          <div class="value">${summary.failed}</div>
        </article>
        <article class="summary-item">
          <div class="label">Skipped</div>
          <div class="value">${summary.skipped}</div>
        </article>
        <article class="summary-item">
          <div class="label">Timed Out</div>
          <div class="value">${summary.timedOut}</div>
        </article>
        <article class="summary-item">
          <div class="label">Interrupted</div>
          <div class="value">${summary.interrupted}</div>
        </article>
        <article class="summary-item">
          <div class="label">Unknown</div>
          <div class="value">${summary.unknown}</div>
        </article>
      </section>

      ${runMetadataHtml}

      ${globalErrorsHtml}

      <section class="tests">
        ${rowsHtml}
      </section>
    </main>
  </body>
</html>`;
}

async function ensureDirectory(filePath) {
  const dir = path.dirname(filePath);
  await fs.mkdir(dir, { recursive: true });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const cwd = process.cwd();
  const jsonPath = path.resolve(cwd, args.jsonPath);
  const outputPath = path.resolve(cwd, args.outputPath);

  if (!(await fileExists(jsonPath))) {
    console.error(`[pdf-report] JSON report not found: ${jsonPath}`);
    process.exit(1);
  }

  const rawJson = await fs.readFile(jsonPath, "utf-8");
  const jsonData = JSON.parse(rawJson);
  const allEntries = flattenSuites(jsonData.suites || []);
  const {
    includedEntries: entries,
    excludedCount,
    excludedProjects,
  } = filterEntriesByProject(allEntries, args.excludeProjects);
  const summary = buildSummary(entries);
  const globalErrorsHtml = buildGlobalErrorsHtml(jsonData.errors || []);
  const rowsHtml = await buildTestRowsHtml(cwd, entries);
  const generatedAt = new Date().toISOString();

  const runMetadata = {
    testType: args.testType,
    baseURL: args.baseURL,
    runCommand: args.runCommand,
    gitSha: args.gitSha,
    startedAt: jsonData?.stats?.startTime || "",
    durationMs: Number(jsonData?.stats?.duration || 0),
    expected: jsonData?.stats?.expected ?? "",
    unexpected: jsonData?.stats?.unexpected ?? "",
    flaky: jsonData?.stats?.flaky ?? "",
    excludedProjects: excludedProjects.join(", "),
    excludedCount,
    workers: jsonData?.config?.workers ?? "",
    configFile: jsonData?.config?.configFile ?? "",
    jsonSourcePath: jsonPath,
    jsonArchivePath: args.jsonArchivePath || "",
  };
  const runMetadataHtml = buildRunMetadataHtml(runMetadata);

  const html = buildHtmlDocument({
    title: args.title,
    generatedAt,
    summary,
    rowsHtml,
    globalErrorsHtml,
    runMetadataHtml,
  });

  await ensureDirectory(outputPath);
  const tempHtmlPath = path.join(tmpdir(), `e2e-pdf-report-${Date.now()}.html`);
  await fs.writeFile(tempHtmlPath, html, "utf-8");

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(tempHtmlPath).href, {
      waitUntil: "networkidle",
    });
    await page.pdf({
      path: outputPath,
      format: "A4",
      printBackground: true,
      margin: {
        top: "10mm",
        right: "10mm",
        bottom: "10mm",
        left: "10mm",
      },
    });
  } finally {
    await browser.close();
    await fs.rm(tempHtmlPath, { force: true });
  }

  process.stdout.write(`[pdf-report] Generated: ${outputPath}\n`);
}

main().catch((error) => {
  console.error("[pdf-report] Failed to generate report");
  console.error(error);
  process.exit(1);
});
