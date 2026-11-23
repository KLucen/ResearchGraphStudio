import { setAppearance, useAppearance, type Appearance } from "./appearance";

const appearances: ReadonlyArray<{ value: Appearance; label: string }> = [
  { value: "system", label: "跟随系统" },
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
];

export function AppearanceSettings() {
  const appearance = useAppearance();
  return (
    <section
      className="settings-card appearance-card"
      aria-labelledby="appearance-title"
    >
      <h2 id="appearance-title">外观</h2>
      <fieldset className="appearance-options">
        <legend>应用主题</legend>
        {appearances.map(({ value, label }) => (
          <label key={value}>
            <input
              type="radio"
              name="rgs-appearance"
              checked={appearance === value}
              onChange={() => setAppearance(value)}
            />
            {label}
          </label>
        ))}
      </fieldset>
    </section>
  );
}
