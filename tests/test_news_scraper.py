from __future__ import annotations

from market.news_scraper import InvestingCalendarClient


def test_parse_events_filters_usd_high_impact_rows():
    html = """
    <table>
      <tr class="js-event-item">
        <td class="time">15:30</td>
        <td class="flagCur">USD</td>
        <td class="event">Initial Jobless Claims</td>
        <td class="forecast">210K</td>
        <td class="previous">211K</td>
        <td><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i></td>
      </tr>
      <tr class="js-event-item">
        <td class="time">17:00</td>
        <td class="flagCur">USD</td>
        <td class="event">Manufacturing PMI</td>
        <td class="forecast">51.2</td>
        <td class="previous">50.8</td>
        <td><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i></td>
      </tr>
      <tr class="js-event-item">
        <td class="time">21:00</td>
        <td class="flagCur">USD</td>
        <td class="event">FOMC Minutes</td>
        <td class="forecast"></td>
        <td class="previous"></td>
        <td><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i></td>
      </tr>
      <tr class="js-event-item">
        <td class="time">12:00</td>
        <td class="flagCur">EUR</td>
        <td class="event">German CPI</td>
        <td class="forecast">2.1%</td>
        <td class="previous">2.2%</td>
        <td><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i><i class="grayFullBullishIcon"></i></td>
      </tr>
    </table>
    """
    events = InvestingCalendarClient.parse_events(html)
    usd_events = [event for event in events if event.currency == "USD" and event.impact >= 3]
    assert len(usd_events) == 3
    assert usd_events[0].title == "Initial Jobless Claims"
    assert usd_events[1].forecast == "51.2"
