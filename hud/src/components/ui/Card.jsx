export function Card({ title, icon: Icon, action, className = "", children }) {
  return (
    <section
      className={`rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-lg shadow-black/20 ${className}`}
    >
      {title && (
        <header className="mb-4 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
            {Icon && <Icon className="h-4 w-4" aria-hidden />}
            {title}
          </h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
