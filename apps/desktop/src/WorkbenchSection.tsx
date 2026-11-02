import { useState, type ReactNode } from "react";

export function WorkbenchSection({
  projectId,
  id,
  title,
  description,
  children,
}: {
  projectId: string;
  id: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  const key = `rgs.papers.${projectId}.${id}.open`;
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(key) !== "false";
    } catch {
      return true;
    }
  });
  return (
    <section className="workbench-section" aria-label={title}>
      <h2>
        <button
          className="section-disclosure"
          aria-expanded={open}
          aria-controls={`paper-section-${id}`}
          onClick={() => {
            setOpen(!open);
            try {
              localStorage.setItem(key, String(!open));
            } catch {
              /* Session state still works without storage. */
            }
          }}
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          {title}
          <small>{description}</small>
        </button>
      </h2>
      <div
        id={`paper-section-${id}`}
        hidden={!open}
        className="workbench-section-body"
      >
        {children}
      </div>
    </section>
  );
}
