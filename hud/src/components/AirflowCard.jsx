import { Wind } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Slider } from "@/components/ui/Slider";

export function AirflowCard({ settings, onChange }) {
  return (
    <Card title="Humidity & airflow" icon={Wind}>
      <div className="space-y-5">
        <Slider
          label="Target humidity"
          value={settings.target_humidity_pct}
          unit="%"
          accent="teal"
          onCommit={(v) => onChange({ target_humidity_pct: v })}
        />
        <Slider
          label="Fan speed"
          value={settings.fan_speed_pct}
          unit="%"
          accent="sky"
          onCommit={(v) => onChange({ fan_speed_pct: v })}
        />
      </div>
    </Card>
  );
}
