import type { Creative } from "../types";

// Предпросмотр креатива в макете экрана телефона.
export default function Preview({ creatives }: { creatives: Creative[] }) {
  if (!creatives.length) return null;
  return (
    <div className="card">
      <h2>Предпросмотр</h2>
      <div className="previews">
        {creatives.map((c, i) => (
          <figure key={c.id ?? i}>
            <div className="phone">
              <div className="phone-bar">9:41</div>
              {c.type === "push" ? (
                <div className="push">
                  <b>{c.title}</b>
                  <span>{c.text}</span>
                </div>
              ) : (
                <div className={`banner ${c.type}`}>
                  {c.image_url && <img src={c.image_url} alt="" />}
                  <div className="banner-body">
                    <b>{c.title}</b>
                    {c.text && <span>{c.text}</span>}
                    {c.button && <button>{c.button}</button>}
                  </div>
                  <small className="ad-mark">Реклама</small>
                </div>
              )}
            </div>
            <figcaption>
              {c.placement_id} {c.variant && `· вариант ${c.variant}`}
              {c.issues && c.issues.length > 0 && (
                <ul className="issues">{c.issues.map((x) => <li key={x}>{x}</li>)}</ul>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
}
