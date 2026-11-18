// dsh-sleuth-analyzers —— 八个外部分析器的接入层（宿主半）。
//
// 职责边界：
//   仓库侧（本文件）只做「解析 python、预检实现、跑入口、超时、截断、落结果、返回摘要」。
//   分析器本身是 tools/<name>/ 下的 Python 实现，按 packages 分发，本文件不含任何判据。
//
// 三行语义（见 cordis.patch.yml）：
//   mode: tools    → 注册 sleuth_analyze
//   mode: analyzer → 把某个分析器登记为「允许被调用」（一行一个，关掉即视为不存在）
//   mode: settings → 只提供状态查询路由，不注册工具
//
// 失败一律返回 ok:false + reason，不抛异常：诊断流程按 reason 决定退化，不做重试。

import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

let defineTool
let sdkDefineTool = null
try {
  sdkDefineTool = (await import('@deepseek-ai/dsh-tools')).defineTool
} catch {
  sdkDefineTool = null
}
// defineTool 有方言差异：真品只认 value schema DSL（属性级 required: true），
// 拿不到真品时输出面按 JSON Schema 校验（required 必须是 object 层的数组）。
// 这里的 output.schema 源码按 JSON Schema 写（顶层 required: [...]），
// 真品路径转成 DSL、回退路径原样交出；缺这层，两条路径总有一条拒绝。
function plainDefineTool(options) {
  return {
    name: options.name,
    description: options.description,
    parameters: options.parameters,
    output: { schema: options.output.schema, render: options.output.render },
    execute: options.execute,
  }
}
function outputSchemaAsDSL(schema) {
  if (!schema || schema.type !== 'object' || typeof schema.properties !== 'object' || schema.properties === null) return schema
  const required = Array.isArray(schema.required) ? schema.required : []
  const properties = {}
  for (const [key, field] of Object.entries(schema.properties)) {
    const copy = Object.assign({}, field)
    if (required.indexOf(key) >= 0) copy.required = true
    properties[key] = copy
  }
  const dsl = { type: 'object', properties }
  if (Object.hasOwn(schema, 'additionalProperties')) dsl.additionalProperties = schema.additionalProperties
  return dsl
}
function wrapDefineTool(options) {
  if (sdkDefineTool === null) return plainDefineTool(options)
  return sdkDefineTool(Object.assign({}, options, {
    output: Object.assign({}, options.output, { schema: outputSchemaAsDSL(options.output.schema) }),
  }))
}
defineTool = wrapDefineTool

export const name = 'sleuth-analyzers'
export const inject = ['tools']

const HERE = path.dirname(fileURLToPath(import.meta.url))
const TOOLS_DIR = path.join(HERE, 'tools')
const ANALYSIS_ENTRY = 'run.py'
const DEFAULT_BUDGET_MS = 10 * 60 * 1000
const SUMMARY_LIMIT = 500
const FINDING_LIMIT = 5
const FINDING_CHAR_LIMIT = 200
const STATE_SCHEMA = 1

const KNOWN = [
  'ibmc_analyzer',
  'prof-compare',
  'cluster-analysis',
  'cluster-compare',
  'issue-analyzer',
  'ascend-dump-analyzer',
  'cpu-host-performance',
  'vllm-ascend-tuning',
]

const ENABLED = new Set()
let config = {}

const OUTPUT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['ok'],
  properties: {
    ok: { type: 'boolean' },
    reason: { type: 'string' },
    detail: { type: 'string' },
    analyzer: { type: 'string' },
    analyzer_version: { type: 'string' },
    status: { type: 'string' },
    summary: { type: 'string' },
    findings: { type: 'array', items: { type: 'string' } },
    missing: { type: 'array', items: { type: 'string' } },
    result_file: { type: 'string' },
    artifacts: { type: 'array', items: { type: 'string' } },
    duration_ms: { type: 'integer' },
    truncated: { type: 'boolean' },
  },
}

function stateRoot() {
  const configured = config.stateDir || process.env.DSH_SLEUTH_STATE_DIR || ''
  if (configured) return path.resolve(configured, 'traces', 'evidence')
  return path.join(os.tmpdir(), 'sleuth-analyzers', 'traces', 'evidence')
}

function analyzerDir(analyzer) {
  return path.join(TOOLS_DIR, analyzer)
}

function hasImplementation(analyzer) {
  const entry = path.join(analyzerDir(analyzer), ANALYSIS_ENTRY)
  return existsSync(entry)
}

function clip(text, limit) {
  const value = String(text || '')
  return value.length <= limit ? value : `${value.slice(0, limit)}\n……已截断（${value.length} 字符中保留 ${limit}）`
}

function runProcess(candidate, args, timeoutMs) {
  return new Promise((resolve) => {
    const started = Date.now()
    let stdout = ''
    let stderr = ''
    let settled = false
    const finish = (value) => {
      if (settled) return
      settled = true
      resolve({ elapsed_ms: Date.now() - started, stdout, stderr, ...value })
    }
    let child
    try {
      child = spawn(candidate, args, { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
    } catch (error) {
      finish({ ok: false, phase: 'spawn-threw', error: String((error && error.code) || error), message: String((error && error.message) || '') })
      return
    }
    const timer = setTimeout(() => {
      try { child.kill('SIGKILL') } catch { /* 已退出 */ }
      if (process.platform === 'win32' && child.pid) {
        try { spawn('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore', windowsHide: true }) } catch { /* 尽力 */ }
      }
      finish({ ok: false, phase: 'timeout' })
    }, timeoutMs)
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
    child.on('error', (error) => {
      clearTimeout(timer)
      finish({ ok: false, phase: 'child-error', error: String((error && error.code) || error), message: String((error && error.message) || '') })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      finish({ ok: code === 0, phase: 'closed', exit_code: code })
    })
  })
}

async function resolvePython() {
  const candidates = [['python3', []], ['python', []], ['py', ['-3']]]
  const tried = []
  for (const [cmd, prefix] of candidates) {
    const probe = await runProcess(cmd, [...prefix, '-c', 'print(1)'], 8000)
    tried.push(`${cmd}${prefix.length ? ` ${prefix.join(' ')}` : ''}: ${probe.ok ? 'ok' : `${probe.phase}${probe.error ? `/${probe.error}` : ''}`}`)
    if (probe.ok) return { python: cmd, prefix, tried }
  }
  return { python: null, tried }
}

function normalizeInputs(inputs) {
  const list = Array.isArray(inputs) ? inputs : [inputs].filter(Boolean)
  const resolved = []
  const missing = []
  for (const item of list) {
    const value = String(item || '').trim()
    if (!value) continue
    if (!path.isAbsolute(value)) {
      missing.push(`${value}（不是绝对路径）`)
      continue
    }
    if (!existsSync(value)) {
      missing.push(`${value}（不存在）`)
      continue
    }
    resolved.push({ path: value, kind: statSync(value).isDirectory() ? 'dir' : 'file' })
  }
  return { resolved, missing }
}

function readAnalyzerMeta(analyzer) {
  const empty = { version: 'unknown', upstream_commit: 'unknown' }
  const file = path.join(analyzerDir(analyzer), 'meta.json')
  if (!existsSync(file)) return empty
  try {
    const meta = JSON.parse(readFileSync(file, 'utf8'))
    return {
      version: String(meta.version || 'unknown'),
      upstream_commit: String(meta.upstream_commit || 'unknown'),
    }
  } catch {
    return empty
  }
}

function responder(value) {
  if (!value.ok) {
    const lines = [`分析器调用未完成：${value.reason || 'unknown'}`]
    if (value.detail) lines.push(value.detail)
    lines.push('按 analyzer-dispatch 的退化规则回到原路径，本单不重试；不要把它记成「已排除」。')
    return lines
  }
  const lines = [
    `分析器：${value.analyzer}｜版本：${value.analyzer_version || 'unknown'}｜状态：${value.status}｜耗时：${(value.duration_ms / 1000).toFixed(1)} s`,
  ]
  lines.push(value.summary || '（分析器没有给摘要）')
  if (value.findings && value.findings.length) {
    lines.push('关键发现：')
    value.findings.forEach((item, index) => {
      lines.push(`${index + 1}. ${item}`)
    })
  }
  if (value.missing && value.missing.length) lines.push(`缺数据：${value.missing.join('；')}`)
  if (value.artifacts && value.artifacts.length) lines.push(`报告与产物：${value.artifacts.join('、')}`)
  if (value.result_file) lines.push(`结构化结果：${value.result_file}`)
  if (value.truncated) lines.push('（摘要已按预算截断；全文在结构化结果里）')
  return lines
}

async function analyze(args) {
  const analyzer = String(args.analyzer || '').trim()
  if (!KNOWN.includes(analyzer)) {
    return { ok: false, reason: 'unknown-analyzer', detail: `可用的分析器名：${KNOWN.join('、')}` }
  }
  if (!ENABLED.has(analyzer)) {
    return { ok: false, reason: 'analyzer-disabled', detail: `插件里 ${analyzer} 那一行没开；诊断走原路径。` }
  }
  if (!hasImplementation(analyzer)) {
    return { ok: false, reason: 'analyzer-not-installed', detail: `${analyzer} 的实现还没随包分发（缺 tools/${analyzer}/${ANALYSIS_ENTRY}）。` }
  }

  const { resolved, missing } = normalizeInputs(args.inputs)
  if (!resolved.length) {
    return missing.length
      ? { ok: false, reason: 'bad-input', detail: `路径都不能用：${missing.join('；')}` }
      : { ok: false, reason: 'no-input', detail: '没有给绝对路径。' }
  }
  if (missing.length) {
    return { ok: false, reason: 'bad-input', detail: `以下路径不能用，其余也未分析，请修正后重跑：${missing.join('；')}` }
  }

  const python = await resolvePython()
  if (!python.python) {
    return { ok: false, reason: 'no-python', detail: `候选都试过：${python.tried.join('；')}` }
  }

  const callId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
  const sessionId = String(args.session_id || 'manual').replace(/[^A-Za-z0-9._-]/g, '_')
  const outDir = path.join(stateRoot(), sessionId, 'tool-runs', callId)
  mkdirSync(outDir, { recursive: true })

  const budgetMs = Number(args.budget_seconds) > 0 ? Math.min(Number(args.budget_seconds) * 1000, 60 * 60 * 1000) : (config.budgetMs || DEFAULT_BUDGET_MS)
  const meta = readAnalyzerMeta(analyzer)
  const started = Date.now()
  const entry = path.join(analyzerDir(analyzer), ANALYSIS_ENTRY)
  const result = await runProcess(python.python, [
    ...python.prefix,
    entry,
    '--inputs', JSON.stringify(resolved.map((item) => item.path)),
    '--out-dir', outDir,
    '--ab', String(args.ab || ''),
    '--purpose', String(args.purpose || ''),
  ], budgetMs)

  writeFileSync(path.join(outDir, 'stdout.log'), result.stdout || '', 'utf8')
  writeFileSync(path.join(outDir, 'stderr.log'), result.stderr || '', 'utf8')
  writeFileSync(path.join(outDir, 'invocation.json'), JSON.stringify({
    schema_version: STATE_SCHEMA,
    analyzer,
    analyzer_version: meta.version,
    upstream_commit: meta.upstream_commit,
    call_id: callId,
    session_id: sessionId,
    inputs: resolved,
    ab: args.ab || '',
    purpose: args.purpose || '',
    budget_ms: budgetMs,
    python: `${python.python}${python.prefix.join(' ')}`,
    started_at: new Date(started).toISOString(),
  }, null, 2), 'utf8')

  const resultFile = path.join(outDir, 'result.json')
  const hasResult = existsSync(resultFile)
  let payload = null
  let parseError = ''
  if (hasResult) {
    try {
      payload = JSON.parse(readFileSync(resultFile, 'utf8'))
    } catch (error) {
      parseError = String((error && error.message) || error)
    }
  }

  if (result.phase !== 'closed' || result.exit_code !== 0) {
    return {
      ok: false,
      reason: result.phase === 'timeout' ? 'timeout' : 'analyzer-failed',
      detail: [
        `退出码 ${result.exit_code === undefined ? '-' : result.exit_code}；产物目录 ${outDir}`,
        hasResult ? '有 result.json 但进程没正常结束，不采信' : '',
        clip(result.stderr, 300),
      ].filter(Boolean).join('；'),
    }
  }

  if (!hasResult) {
    return {
      ok: false,
      reason: 'no-result',
      detail: `进程正常结束但没有写 result.json；产物目录 ${outDir}`,
    }
  }

  if (parseError) {
    return {
      ok: false,
      reason: 'bad-result-json',
      detail: `result.json 解析失败：${clip(parseError, 200)}；产物目录 ${outDir}`,
    }
  }

  const analyzerStatus = String((payload && payload.status) || 'ok')
  if (analyzerStatus === 'failed' || analyzerStatus === 'blocked') {
    return {
      ok: false,
      reason: `analyzer-${analyzerStatus}`,
      detail: clip(String((payload && payload.summary) || '分析器自报未完成'), SUMMARY_LIMIT),
      result_file: resultFile,
    }
  }

  const rawSummary = String((payload && payload.summary) || '（分析器没有给摘要）')
  const rawFindings = Array.isArray(payload && payload.findings)
    ? payload.findings.map((item) => (typeof item === 'string' ? item : (item && item.claim) || '')).filter(Boolean)
    : []
  const summary = clip(rawSummary, SUMMARY_LIMIT)
  const findings = rawFindings.slice(0, FINDING_LIMIT).map((item) => clip(item, FINDING_CHAR_LIMIT))
  const truncated = summary !== rawSummary
    || rawFindings.length > findings.length
    || findings.some((item, index) => item !== rawFindings[index])
  return {
    ok: true,
    analyzer,
    analyzer_version: String((payload && payload.analyzer_version) || meta.version),
    status: analyzerStatus,
    summary,
    findings,
    missing: Array.isArray(payload && payload.missing) ? payload.missing.slice(0, FINDING_LIMIT) : [],
    result_file: resultFile,
    artifacts: Array.isArray(payload && payload.artifacts) ? payload.artifacts.map(String).slice(0, 20) : [],
    duration_ms: Date.now() - started,
    truncated,
  }
}

function registerSettings(ctx) {
  ctx.inject(['webServer'], (webCtx) => {
    const route = {
      kind: 'prefix',
      path: '/sleuth-analyzers/api',
      handler: async (req, res) => {
        const send = (status, payload) => {
          res.setHeader('Content-Type', 'application/json; charset=utf-8')
          res.writeHead(status)
          res.end(JSON.stringify(payload))
        }
        if (!/\/status$/.test(String(req.url || ''))) {
          send(404, { error: 'not found' })
          return
        }
        const python = await resolvePython()
        send(200, {
          schema_version: STATE_SCHEMA,
          state_root: stateRoot(),
          python: python.python ? `${python.python}${python.prefix.join(' ')}` : null,
          python_tried: python.tried,
          analyzers: KNOWN.map((item) => ({ analyzer: item, enabled: ENABLED.has(item), installed: hasImplementation(item) })),
        })
      },
    }
    webCtx.effect(() => webCtx.webServer.register(route), 'sleuth-analyzers: 状态查询')
  })
}

function registerTools(ctx) {
  ctx.tools.register(defineTool({
    name: 'sleuth_analyze',
    description: '调用已安装的外部分析器分析工程师交来的整包数据（prof 目录、dump_info、日志包、ftrace 采集包），返回结构化摘要与证据文件路径。只在 diagnose 步骤 5 或用户点名分析时用；数据形态选择见 skills/diagnose/references/analyzer-dispatch.md。工具不在或返回 ok:false 时走原路径，不重试。',
    parameters: {
      analyzer: { type: 'string', required: true, description: `分析器名：${KNOWN.join(' / ')}` },
      inputs: { type: 'string', required: true, description: '数据的绝对路径，多个用换行分隔（目录或文件）。必须是本机路径，不接受 URL。' },
      purpose: { type: 'string', description: '这次要回答的问题，一句话；写进调用记录' },
      ab: { type: 'string', description: '两组数据比对时标基准：写 A 或 B，对应 inputs 里的两个路径；单份分析不填' },
      session_id: { type: 'string', description: '当前诊断的 session_id；手动调用不填则记为 manual' },
      budget_seconds: { type: 'integer', description: '超时上限，默认 600 秒' },
    },
    output: {
      schema: OUTPUT_SCHEMA,
      render: (_args, value) => [{ type: 'text', text: responder(value).join('\n') }],
    },
    async execute(args) {
      const inputs = String(args.inputs || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
      return analyze({ ...args, inputs })
    },
  }))
}

export function apply(ctx, blockConfig = {}) {
  if (blockConfig && blockConfig.mode === 'analyzer') {
    if (KNOWN.includes(blockConfig.analyzer)) ENABLED.add(blockConfig.analyzer)
    return
  }
  if (blockConfig && blockConfig.mode === 'settings') {
    config = blockConfig
    registerSettings(ctx)
    return
  }
  if (blockConfig && blockConfig.mode === 'tools') {
    config = blockConfig
    registerTools(ctx)
  }
}
