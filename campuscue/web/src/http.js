import { apiErrorMessage } from './boardState.js'

export const DEFAULT_TIMEOUT_MS = 15_000

async function responseReason(response) {
  const fallback = `${response.status} ${response.statusText}`.trim()
  try {
    const body = await response.json()
    const detail = body?.detail ?? body?.message
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => item?.msg).filter(Boolean)
      if (messages.length) {
        return messages.join('；').replace(/Value error, /g, '')
      }
    }
  } catch {
    // The status line is the only safe fallback for a non-JSON error body.
  }
  return fallback
}

export async function requestJson(
  url,
  options = {},
  {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    fetchImpl = globalThis.fetch,
    online = globalThis.navigator?.onLine !== false,
  } = {},
) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const { headers = {}, ...request } = options
  try {
    const response = await fetchImpl(url, {
      credentials: 'same-origin',
      ...request,
      headers: { 'Content-Type': 'application/json', ...headers },
      signal: controller.signal,
    })
    if (!response.ok) {
      const failure = new Error(
        apiErrorMessage({
          status: response.status,
          statusText: response.statusText,
          detail: await responseReason(response),
        }),
      )
      failure.fromApi = true
      throw failure
    }
    if (response.status === 204) return null
    try {
      return await response.json()
    } catch {
      const failure = new Error('服务返回了无法读取的数据，请重启课讯后重试')
      failure.fromApi = true
      throw failure
    }
  } catch (error) {
    if (error?.fromApi) throw error
    throw new Error(
      apiErrorMessage({
        aborted: error?.name === 'AbortError' || controller.signal.aborted,
        online,
      }),
    )
  } finally {
    clearTimeout(timeout)
  }
}

export default requestJson
