"use client";

import { landingCopy, type LandingLocale } from "./landing-copy";
import styles from "./accountant-section.module.css";
import { useDemoDates } from "./use-demo-dates";

export function AccountantSection({ locale }: { locale: LandingLocale }) {
  const copy = landingCopy[locale].accountant;
  const dates = useDemoDates(locale);
  return (
    <section className={styles.section} aria-labelledby="accountant-title">
      <div className={styles.split}>
        <div>
          <h2 id="accountant-title">{copy.title}</h2>
          <p className={styles.body}>{copy.body}</p>
          <ul className={styles.checks}>
            {copy.checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        </div>
        <div className={styles.ledger}>
          <div className={styles.head}>
            <b data-ledger-month>
              {copy.ledger.form} · {dates.month}
            </b>
            <span className={styles.status}>{copy.ledger.status}</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>{copy.ledger.columns[0]}</th>
                <th>{copy.ledger.columns[1]}</th>
                <th className={styles.num}>{copy.ledger.columns[2]}</th>
              </tr>
            </thead>
            <tbody>
              {copy.ledger.rows.map(([rnc, ncf, amount]) => (
                <tr key={ncf}>
                  <td>{rnc}</td>
                  <td>{ncf}</td>
                  <td className={styles.num}>{amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className={styles.foot}>
            <span>{copy.ledger.count}</span>
            <span className={styles.action}>{copy.ledger.action}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
