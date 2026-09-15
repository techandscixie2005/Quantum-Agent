/** Retired parallel teaching APIs. Python owns episodes, science and persistence. */
export function retiredLegacyEndpoint() {
  return Response.json({
    error: "legacy_teaching_endpoint_retired",
    message: "请使用 /agent 学习工作台；教学、科学验证和学习记录由 Python API 统一处理。",
  }, { status: 410 });
}
