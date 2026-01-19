"""
Daily snapshot generator for Vietnamese Bond Data Lab
Produces Vietnamese-language daily summaries
"""
import logging
from datetime import date, timedelta
from typing import Dict, Any, Optional
import json

logger = logging.getLogger(__name__)


class DailySnapshotGenerator:
    """Generate daily snapshot in Vietnamese"""

    # Bucket descriptions in Vietnamese
    BUCKET_DESC_VN = {
        'B0': 'Rất thuận lợi - Thanh khoản dồi dào, áp lực lãi suất thấp',
        'B1': 'Thuận lợi - Thanh khoản tốt, lãi suất ổn định',
        'B2': 'Trung lập - Cân bằng giữa cung và cầu',
        'B3': 'Thắt chặt - Thanh khoản hạn chế, áp lực tăng',
        'B4': 'Rất thắt chặt - Thanh khoản rất căng thẳng, rủi ro cao'
    }

    # Alert type translations
    ALERT_TYPE_VN = {
        'ALERT_LIQUIDITY_SPIKE': 'Đột biến thanh khoản',
        'ALERT_CURVE_BEAR_STEEPEN': 'Độ cong đường lãi suất tăng mạnh',
        'ALERT_AUCTION_WEAK': 'Phát hành yếu',
        'ALERT_TURNOVER_DROP': 'Thanh khoản thị trường thứ cấp giảm',
        'ALERT_POLICY_CHANGE': 'Thay đổi chính sách'
    }

    # Severity translations
    SEVERITY_VN = {
        'HIGH': 'CAO',
        'MEDIUM': 'TRUNG BÌNH',
        'LOW': 'THẤP'
    }

    def __init__(self, db_manager):
        self.db = db_manager

    def generate_snapshot(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Generate daily snapshot data

        Returns:
            dict with sections: tom_tat, so_voi_hom_qua, dien_giai, watchlist, ghi_chu
        """
        if target_date is None:
            target_date = date.today()

        logger.info(f"Generating daily snapshot for {target_date}")

        # Get baseline date using new baseline utilities
        from app.analytics.baseline import get_previous_available_date, get_baseline_data, compute_deltas

        baseline_date = get_previous_available_date(self.db, target_date)

        # Get latest transmission metrics
        latest_metrics = self.db.get_transmission_metrics(
            start_date=str(target_date),
            end_date=str(target_date)
        )

        # Get baseline data if available
        baseline_data = None
        if baseline_date:
            baseline_data = get_baseline_data(self.db, baseline_date)

        # Get recent alerts
        recent_alerts = self.db.get_transmission_alerts(
            start_date=str(target_date - timedelta(days=7)),
            end_date=str(target_date),
            limit=20
        )

        # Build snapshot sections
        snapshot = {
            'date': str(target_date),
            'baseline_date': str(baseline_date) if baseline_date else None,
            'tom_tat': self._generate_tom_tat(latest_metrics),
            'so_voi_hom_qua': self._generate_so_voi_hom_qua(latest_metrics, baseline_data),
            'dien_giai': self._generate_dien_giai(latest_metrics),
            'watchlist': self._generate_watchlist(recent_alerts, latest_metrics),
            'ghi_chu': self._generate_ghi_chu(latest_metrics)
        }

        # Persist snapshot to database
        try:
            import json
            self.db.insert_daily_snapshot(
                date=str(target_date),
                baseline_date=str(baseline_date) if baseline_date else None,
                snapshot_json=json.dumps(snapshot, ensure_ascii=False, indent=2),
                source_components={
                    'metrics_count': len(latest_metrics),
                    'alerts_count': len(recent_alerts),
                    'baseline_available': baseline_date is not None
                }
            )
            logger.info(f"Persisted daily snapshot for {target_date} (baseline: {baseline_date})")
        except Exception as e:
            logger.error(f"Failed to persist snapshot: {e}")
            # Continue anyway - snapshot is still returned

        return snapshot

    def _generate_tom_tat(self, metrics: list) -> Dict[str, Any]:
        """Generate Tóm tắt (Summary) section"""
        # Extract key metrics
        metric_dict = {m['metric_name']: m['metric_value'] for m in metrics if m['metric_value'] is not None}

        score = metric_dict.get('transmission_score')
        bucket = metric_dict.get('regime_bucket')
        level_10y = metric_dict.get('level_10y')
        slope_10y_2y = metric_dict.get('slope_10y_2y')
        ib_on = metric_dict.get('ib_on')

        return {
            'diem_so': score,
            'nhom': bucket,
            'mo_ta': self.BUCKET_DESC_VN.get(bucket, 'Không có dữ liệu'),
            'lai_suat_10y': level_10y,
            'do_cong': slope_10y_2y,
            'lai_suat_qua_dem': ib_on
        }

    def _generate_so_voi_hom_qua(self, current_metrics: list, baseline_data: dict) -> Dict[str, Any]:
        """Generate So với hôm qua (Compared to baseline) section"""
        current_dict = {m['metric_name']: m['metric_value'] for m in current_metrics if m['metric_value'] is not None}

        # Extract baseline transmission data
        baseline_dict = baseline_data.get('transmission', {}) if baseline_data else {}

        changes = {}
        baseline_date = baseline_data.get('date') if baseline_data else None

        # Score change
        if 'transmission_score' in current_dict and 'transmission_score' in baseline_dict:
            score_change = current_dict['transmission_score'] - baseline_dict['transmission_score']
            changes['diem_so'] = {
                'hien_tai': current_dict['transmission_score'],
                'baseline': baseline_dict['transmission_score'],
                'thay_doi': score_change,
                'xu_huong': 'tăng' if score_change > 0 else 'giảm' if score_change < 0 else 'không đổi'
            }

        # 10Y yield change
        if 'level_10y' in current_dict and 'level_10y' in baseline_dict:
            yield_change = current_dict['level_10y'] - baseline_dict['level_10y']
            changes['lai_suat_10y'] = {
                'hien_tai': current_dict['level_10y'],
                'baseline': baseline_dict['level_10y'],
                'thay_doi': yield_change,
                'xu_huong': 'tăng' if yield_change > 0 else 'giảm' if yield_change < 0 else 'không đổi'
            }

        # Interbank rate change
        if 'ib_on' in current_dict and 'ib_on' in baseline_dict:
            ib_change = current_dict['ib_on'] - baseline_dict['ib_on']
            changes['lai_suat_qua_dem'] = {
                'hien_tai': current_dict['ib_on'],
                'baseline': baseline_dict['ib_on'],
                'thay_doi': ib_change,
                'xu_huong': 'tăng' if ib_change > 0 else 'giảm' if ib_change < 0 else 'không đổi'
            }

        # Curve slope change
        if 'slope_10y_2y' in current_dict and 'slope_10y_2y' in baseline_dict:
            slope_change = current_dict['slope_10y_2y'] - baseline_dict['slope_10y_2y']
            changes['do_cong'] = {
                'hien_tai': current_dict['slope_10y_2y'],
                'baseline': baseline_dict['slope_10y_2y'],
                'thay_doi': slope_change,
                'xu_huong': 'steepening' if slope_change > 0 else 'flattening' if slope_change < 0 else 'không đổi'
            }

        # Include baseline_date in result
        result = {'changes': changes}
        if baseline_date:
            result['baseline_date'] = str(baseline_date)
        else:
            result['message'] = 'Chưa có dữ liệu so sánh'

        return result

    def _generate_dien_giai(self, metrics: list) -> list:
        """Generate Diễn giải (Explanation) section - key insights"""
        metric_dict = {m['metric_name']: m['metric_value'] for m in metrics if m['metric_value'] is not None}

        insights = []

        # Score insight
        score = metric_dict.get('transmission_score')
        if score is not None:
            if score >= 80:
                insights.append("Điểm số truyền dẫn rất cao, thị trường đang chịu áp lực đáng kể.")
            elif score >= 60:
                insights.append("Điểm số truyền dẫn ở mức cao, cần theo dõi sát các yếu tố thanh khoản.")
            elif score >= 40:
                insights.append("Điểm số truyền dẫn ở mức trung lập, thị trường cân bằng.")
            elif score >= 20:
                insights.append("Điểm số truyền dẫn thấp, điều kiện thị trường thuận lợi.")
            else:
                insights.append("Điểm số truyền dẫn rất thấp, thanh khoản dồi dào.")

        # Curve insight
        level_10y = metric_dict.get('level_10y')
        if level_10y is not None:
            insights.append(f"Lãi suất trái phiếu kỳ hạn 10 năm ở mức {level_10y:.2f}%.")

        # Liquidity insight
        ib_on = metric_dict.get('ib_on')
        if ib_on is not None:
            if ib_on > 1.0:
                insights.append(f"Lãi suất qua đêm O/N cao ({ib_on:.2f}%) cho thấy áp lực thanh khoản ngắn hạn.")
            elif ib_on < 0.5:
                insights.append(f"Lãi suất qua đêm O/N thấp ({ib_on:.2f}%) phản ánh thanh khoản dồi dào.")
            else:
                insights.append(f"Lãi suất qua đêm O/N ở mức ({ib_on:.2f}%) ổn định.")

        # Supply insight
        auction_sold = metric_dict.get('auction_sold_total_5d')
        if auction_sold is not None:
            insights.append(f"Khối lượng phát hành 5 ngày gần nhất: {auction_sold:.0f} tỷ đồng.")

        # Demand insight
        secondary_value = metric_dict.get('secondary_value_total_5d')
        if secondary_value is not None:
            insights.append(f"Khối lượng giao dịch thứ cấp 5 ngày gần nhất: {secondary_value:.0f} tỷ đồng.")

        return insights

    def _generate_watchlist(self, alerts: list, metrics: list) -> list:
        """Generate Watchlist section - key items to monitor"""
        watchlist = []

        # Add active alerts
        if alerts:
            for alert in alerts[:5]:  # Top 5 recent alerts
                watchlist.append({
                    'loai': self.ALERT_TYPE_VN.get(alert['alert_type'], alert['alert_type']),
                    'muc_do': self.SEVERITY_VN.get(alert['severity'], alert['severity']),
                    'noi_dung': alert['message'],
                    'ngay': alert['date']
                })

        # Add metric-based watch items
        metric_dict = {m['metric_name']: m['metric_value'] for m in metrics if m['metric_value'] is not None}

        # High interbank rate
        if metric_dict.get('ib_on', 0) > 1.0:
            watchlist.append({
                'loai': 'Thanh khoản',
                'muc_do': 'CAO',
                'noi_dung': 'Lãi suất qua đêm vượt 1.0%',
                'ngay': str(date.today())
            })

        # Low auction bid-to-cover
        if metric_dict.get('auction_bid_to_cover_median_20d', 2) < 1.2:
            watchlist.append({
                'loai': 'Phát hành',
                'muc_do': 'TRUNG BÌNH',
                'noi_dung': 'Tỷ lệ thầu/đấu thấp',
                'ngay': str(date.today())
            })

        # Steepening curve
        if metric_dict.get('slope_10y_2y', 0) > 2.0:
            watchlist.append({
                'loai': 'Đường lãi suất',
                'muc_do': 'TRUNG BÌNH',
                'noi_dung': 'Độ cong 10Y-2Y rộng (>2%)',
                'ngay': str(date.today())
            })

        return watchlist

    def _generate_ghi_chu(self, metrics: list) -> list:
        """Generate Ghi chú (Notes) section - data quality and availability"""
        notes = []

        metric_dict = {m['metric_name']: m['metric_value'] for m in metrics}

        # Check data availability
        if not metric_dict.get('transmission_score'):
            notes.append("⚠️ Chưa có điểm số truyền dẫn. Hãy chạy tính toán analytics.")

        if not metric_dict.get('level_10y'):
            notes.append("⚠️ Thiếu dữ liệu đường lãi suất trái phiếu.")

        if not metric_dict.get('ib_on'):
            notes.append("⚠️ Thiếu dữ liệu lãi suất liên ngân hàng.")

        if not metric_dict.get('auction_sold_total_5d'):
            notes.append("⚠️ Thiếu dữ liệu phát hành trái phiếu.")

        if not metric_dict.get('secondary_value_total_5d'):
            notes.append("⚠️ Thiếu dữ liệu giao dịch thứ cấp.")

        # Add methodology note
        notes.append("ℹ️ Điểm số truyền dẫn (0-100) là chỉ số tổng hợp từ các yếu tố thanh khoản, cung cầu, và chính sách.")

        return notes
