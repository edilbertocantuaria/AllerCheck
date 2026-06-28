"use client";

import { Info } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from "@/components/ui/tooltip";

interface ParameterControlProps {
  label: string;
  value: number | string;
  onChange: (value: number | string) => void;
  min?: number;
  max?: number;
  step?: number;
  tooltip: string;
  type?: "slider" | "input";
}

export function ParameterControl({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.1,
  tooltip,
  type = "slider"
}: ParameterControlProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">{label}</span>
          <Tooltip delayDuration={100}>
            <TooltipTrigger asChild>
              <button className="text-muted-foreground hover:text-primary transition-colors rounded-full p-0.5 hover:bg-primary/10">
                <Info className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="top"
              align="start"
              sideOffset={8}
              className="max-w-[280px] p-3 bg-popover border border-border shadow-lg rounded-lg"
            >
              <p className="text-xs text-popover-foreground leading-relaxed">
                {tooltip}
              </p>
            </TooltipContent>
          </Tooltip>
        </div>
        <span className="text-sm font-mono text-primary font-medium tabular-nums">
          {typeof value === "number" ? value.toFixed(step < 1 ? 1 : 0) : value}
        </span>
      </div>
      {type === "slider" ? (
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground w-6 text-right">
            {min}
          </span>
          <Slider
            value={[Number(value)]}
            onValueChange={(vals) => onChange(vals[0])}
            min={min}
            max={max}
            step={step}
            className="flex-1"
          />
          <span className="text-xs text-muted-foreground w-6">{max}</span>
        </div>
      ) : (
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 bg-muted border-border text-sm"
          placeholder={`Ex: ${label === "stop" ? "\\n, Fim" : "42"}`}
        />
      )}
    </div>
  );
}
