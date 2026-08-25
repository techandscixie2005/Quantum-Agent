"use client";

import Editor from "@monaco-editor/react";

export default function AgentCodeEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Editor
      height="250px"
      defaultLanguage="python"
      value={value}
      onChange={(next) => onChange(next ?? "")}
      theme="vs-light"
      options={{
        automaticLayout: true,
        fontSize: 13,
        lineHeight: 20,
        minimap: { enabled: false },
        padding: { top: 14, bottom: 14 },
        renderLineHighlight: "gutter",
        scrollBeyondLastLine: false,
        wordWrap: "on",
      }}
    />
  );
}

