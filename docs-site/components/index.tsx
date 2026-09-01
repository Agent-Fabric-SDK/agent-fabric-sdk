import React from 'react'
import Link from 'next/link'
import NextImage from 'next/image'

/* Presentation components for the docs pages.
 *
 * Nextra's built-in <Cards> renders the description above the title and only
 * pads the title row, which reads as broken once cards carry real prose. These
 * replace it and cover the other repeated patterns (hero, status pills,
 * diagrams). Styles live in ../styles/globals.css. */

type Tone = 'live' | 'roadmap' | 'neutral' | 'accent'

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode
  tone?: Tone
}) {
  return <span className={`af-badge af-badge-${tone}`}>{children}</span>
}

export function Hero({
  eyebrow,
  title,
  tagline,
  media,
  actions,
}: {
  eyebrow?: React.ReactNode
  title: string
  tagline: React.ReactNode
  media?: React.ReactNode
  actions?: { label: string; href: string; primary?: boolean }[]
}) {
  return (
    <header className="af-hero">
      {eyebrow ? <span className="af-hero-eyebrow">{eyebrow}</span> : null}
      <h1 className="af-hero-title">{title}</h1>
      <p className="af-hero-tagline">{tagline}</p>
      {media ? <div className="af-hero-media">{media}</div> : null}
      {actions?.length ? (
        <div className="af-hero-actions">
          {actions.map(action => (
            <Link
              key={action.href}
              href={action.href}
              className={`af-button af-button-${action.primary ? 'primary' : 'secondary'}`}
            >
              {action.label}
            </Link>
          ))}
        </div>
      ) : null}
    </header>
  )
}

export function CardGrid({
  children,
  columns,
}: {
  children: React.ReactNode
  columns?: 2 | 3
}) {
  return (
    <div className="af-card-grid" data-columns={columns}>
      {children}
    </div>
  )
}

export function Card({
  title,
  href,
  icon,
  badge,
  badgeTone = 'neutral',
  children,
}: {
  title: string
  href?: string
  icon?: React.ReactNode
  badge?: string
  badgeTone?: Tone
  children?: React.ReactNode
}) {
  const inner = (
    <>
      <span className="af-card-head">
        {icon ? <span className="af-card-icon">{icon}</span> : null}
        <span className="af-card-title">{title}</span>
      </span>
      {children ? <span className="af-card-body">{children}</span> : null}
      {badge ? (
        <span className="af-card-badges">
          <Badge tone={badgeTone}>{badge}</Badge>
        </span>
      ) : null}
    </>
  )

  if (!href) {
    return <div className="af-card">{inner}</div>
  }
  return (
    <Link href={href} className="af-card">
      {inner}
    </Link>
  )
}

export function Figure({
  src,
  alt,
  caption,
  width,
  height,
  priority,
}: {
  src: string
  alt: string
  caption?: React.ReactNode
  width: number
  height: number
  priority?: boolean
}) {
  return (
    <figure className="af-figure">
      <NextImage
        src={src}
        alt={alt}
        width={width}
        height={height}
        priority={priority}
        sizes="(max-width: 768px) 100vw, 900px"
      />
      {caption ? <figcaption>{caption}</figcaption> : null}
    </figure>
  )
}
