"use client";

interface Parameters {
  frequency_penalty: number;
  presence_penalty: number;
  temperature: number;
  max_tokens: number;
  n: number;
  seed: number;
  stop: string;
}

interface ParametersPanelProps {
  parameters: Parameters;
  onParametersChange: (params: Parameters) => void;
}

export function ParametersPanel({
  parameters,
  onParametersChange
}: ParametersPanelProps) {
  return null;
}
