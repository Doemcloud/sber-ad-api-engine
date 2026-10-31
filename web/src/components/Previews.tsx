import { useState } from "react";
import type { BannerContent, PromoComponent, PromoContent, TextStyle } from "../types";

// Цвет #RRGGBBAA → CSS rgba.
export function rgba(c?: string): string | undefined {
  if (!c || !/^#[0-9A-Fa-f]{8}$/.test(c)) return undefined;
  const n = (i: number) => parseInt(c.slice(i, i + 2), 16);
  return `rgba(${n(1)}, ${n(3)}, ${n(5)}, ${(n(7) / 255).toFixed(2)})`;
}

const WEIGHT: Record<string, number> = { thin: 100, light: 300, regular: 400, medium: 500, "semi-bold": 600, bold: 700 };

function textCss(s?: TextStyle, fallbackSize = 14): React.CSSProperties {
  return {
    fontSize: s?.fontSize ?? fallbackSize,
    fontWeight: s?.fontWeight ? WEIGHT[s.fontWeight] : undefined,
    color: rgba(s?.textColor),
  };
}

// В PROMO допустим html-формат; в моках только <b>. Остальное экранируем.
function safeHtml(text: string): string {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/&lt;(\/?)b&gt;/g, "<$1b>");
}

// Картинки из моков на домене .example не резолвятся — показываем подложку.
function Img({ src, className, style }: { src?: string; className?: string; style?: React.CSSProperties }) {
  const [broken, setBroken] = useState(false);
  if (!src || broken) return <div className={`img-fallback ${className ?? ""}`} style={style} aria-label="изображение" />;
  return <img className={className} style={style} src={src} alt="" onError={() => setBroken(true)} />;
}

export function Phone({ children, label }: { children: React.ReactNode; label?: string }) {
  return (
    <figure className="phone-wrap">
      <div className="phone">
        <div className="phone-bar"><span>9:41</span><span>СберБанк Онлайн</span></div>
        <div className="phone-screen">{children}</div>
      </div>
      {label && <figcaption>{label}</figcaption>}
    </figure>
  );
}

export function BannerPreview({ type, content }: { type?: string; content?: BannerContent }) {
  const c = content ?? { actionType: "default" };
  const bg = rgba(c.background?.color);
  if (type === "STORY") {
    return (
      <div className="story" style={{ background: bg ?? "#1f2d27" }}>
        <div className="story-progress"><i /><i /><i /></div>
        {c.image?.url && <Img className="story-img" src={c.image.url} />}
        <div className="story-body">
          {c.title && <div style={textCss(c.titleStyle, 24)} className="story-title">{c.title}</div>}
          {c.text && <div style={textCss(c.textStyle, 14)}>{c.text}</div>}
          {c.buttonName && <button className="story-btn">{c.buttonName}</button>}
        </div>
        <span className="ad-mark">Реклама</span>
      </div>
    );
  }
  return (
    <div className="smart" style={{ background: bg ?? "#ffffff" }}>
      <div className="smart-text">
        {c.title && <div style={textCss(c.titleStyle, 16)} className="smart-title">{c.title}</div>}
        {c.text && <div style={textCss(c.textStyle, 13)}>{c.text}</div>}
        {c.buttonName && <button className="smart-btn">{c.buttonName}</button>}
      </div>
      {c.image?.url && <Img className="smart-img" src={c.image.url} />}
      <span className="ad-mark">Реклама</span>
    </div>
  );
}

function PromoItem({ c }: { c: PromoComponent }) {
  if (c.role === "image") {
    return <Img className="promo-img" src={c.url} style={{ aspectRatio: String(c.aspectRatio ?? 2) }} />;
  }
  if (c.role === "button") {
    return <button className="promo-btn" style={{ background: rgba(c.style?.backgroundColor), ...textCss(c.textStyle, 15) }}>{c.text}</button>;
  }
  if (c.format === "html") {
    return <div style={textCss(c.textStyle, 15)} dangerouslySetInnerHTML={{ __html: safeHtml(c.text ?? "") }} />;
  }
  return <div style={textCss(c.textStyle, 15)}>{c.text}</div>;
}

export function PromoPreview({ content }: { content?: PromoContent }) {
  const lc = content?.component;
  if (!lc) return <div className="hint">Промо-экрана нет</div>;
  return (
    <div className="promo" style={{ background: rgba(lc.style?.backgroundColor) ?? "#fff" }}>
      {(lc.components ?? []).map((c, i) => <PromoItem key={i} c={c} />)}
    </div>
  );
}
