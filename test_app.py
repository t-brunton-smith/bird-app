import unittest
from unittest.mock import patch, MagicMock

import app as ebird_app

FAKE_TWO_ROBIN_RECORDS = [
    {
        'comName': 'American Robin',
        'obsDt': '2026-04-20 08:00',
        'locName': 'Central Park',
        'subId': 'S111111111',
        'howMany': 3,
        'lat': 40.7829,
        'lng': -73.9654,
    },
    {
        'comName': 'American Robin',
        'obsDt': '2026-04-18 07:30',
        'locName': 'Prospect Park',
        'subId': 'S222222222',
        'howMany': 5,
        'lat': 40.6602,
        'lng': -73.9690,
    },
]


class TestURLStrategy(unittest.TestCase):
    """Verify the correct eBird API endpoint is selected for each search variant."""

    @patch('app._fetch_complete_subs')
    @patch('app.requests.get')
    def test_species_specific_url_has_no_detail_full(self, mock_get, mock_complete):
        """Species-specific endpoint must not have detail=full."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[]))
        mock_complete.return_value = set()
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(
                40.71, -74.00,
                species_code='amered',
                species_name='American Robin',
                location='New York',
            )
        called_url = mock_get.call_args[0][0]
        self.assertNotIn('detail=full', called_url)
        self.assertIn('/geo/recent/amered', called_url)

    @patch('app._fetch_complete_subs')
    @patch('app._fetch_all_obs_for_species')
    @patch('app.requests.get')
    def test_no_filter_queries_geo_index_first(self, mock_get, mock_fetch, mock_complete):
        """No species/loc_id: geo/recent index is called first, then per-species fetch."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'American Robin', 'speciesCode': 'amerob',
             'obsDt': '2026-04-20 08:00', 'locName': 'Central Park',
             'subId': 'S111', 'howMany': 3, 'lat': 40.78, 'lng': -73.96},
        ]))
        mock_fetch.return_value = []
        mock_complete.return_value = set()
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(40.71, -74.00, location='New York')
        index_url = mock_get.call_args[0][0]
        self.assertIn('/data/obs/geo/recent', index_url)
        self.assertNotIn('/ref/hotspot/geo', index_url)
        self.assertTrue(mock_fetch.called)

    @patch('app._fetch_complete_subs')
    @patch('app.requests.get')
    def test_empty_index_uses_single_request(self, mock_get, mock_complete):
        """Empty geo index (no species codes) uses index obs directly — only 1 request."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[]))
        mock_complete.return_value = set()
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(40.71, -74.00, location='New York')
        self.assertEqual(mock_get.call_count, 1)
        called_url = mock_get.call_args[0][0]
        self.assertIn('/data/obs/geo/recent', called_url)
        self.assertNotIn('/ref/hotspot/geo', called_url)

    @patch('app._fetch_complete_subs')
    @patch('app.requests.get')
    def test_loc_id_uses_single_direct_request(self, mock_get, mock_complete):
        """Specific hotspot selected: single direct request, no hotspot lookup."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[]))
        mock_complete.return_value = set()
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(
                40.71, -74.00, loc_id='L123456', location='New York')
        self.assertEqual(mock_get.call_count, 1)
        called_url = mock_get.call_args[0][0]
        self.assertIn('L123456/recent', called_url)
        self.assertNotIn('detail=full', called_url)

    @patch('app._fetch_complete_subs')
    @patch('app._fetch_all_obs_for_species')
    @patch('app.requests.get')
    def test_notable_uses_notable_index_then_expands(self, mock_get, mock_fetch, mock_complete):
        """notable=True: notable endpoint used as index, then per-species expansion."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'Painted Bunting', 'speciesCode': 'painbu',
             'obsDt': '2026-04-20 08:00', 'locName': 'Central Park',
             'subId': 'S111', 'howMany': 1, 'lat': 40.78, 'lng': -73.96},
        ]))
        mock_fetch.return_value = []
        mock_complete.return_value = set()
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(40.71, -74.00, notable=True, location='New York')
        self.assertEqual(mock_get.call_count, 1)
        called_url = mock_get.call_args[0][0]
        self.assertIn('/data/obs/geo/recent/notable', called_url)
        self.assertTrue(mock_fetch.called)


class TestGroupingLogic(unittest.TestCase):
    """Verify species grouping, total count, sort order, and hotspot aggregation."""

    @patch('app.render_template')
    @patch('app.requests.get')
    def test_two_checklists_same_species_grouped(self, mock_get, mock_render):
        """Two records for the same species are grouped under one species entry."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=FAKE_TWO_ROBIN_RECORDS))
        mock_render.return_value = ''
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(
                40.71, -74.00, loc_id='L123456', location='New York')
        _, kwargs = mock_render.call_args
        species_data = kwargs['species_data']
        self.assertEqual(len(species_data), 1)
        robin = species_data[0]
        self.assertEqual(robin['name'], 'American Robin')
        self.assertEqual(len(robin['records']), 2,
                         f"Expected 2 records, got {len(robin['records'])}")
        self.assertEqual(robin['total'], 8,
                         f"Expected total=8, got {robin['total']}")
        self.assertEqual(robin['records'][0]['raw_dt'], '2026-04-20 08:00')
        self.assertEqual(robin['records'][1]['raw_dt'], '2026-04-18 07:30')
        self.assertIn('spark_svg', robin)
        self.assertTrue(robin['spark_svg'].startswith('<svg'))

    @patch('app.render_template')
    @patch('app.requests.get')
    def test_total_sightings_count(self, mock_get, mock_render):
        mock_get.return_value = MagicMock(json=MagicMock(return_value=FAKE_TWO_ROBIN_RECORDS))
        mock_render.return_value = ''
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(
                40.71, -74.00, loc_id='L123456', location='New York')
        _, kwargs = mock_render.call_args
        self.assertEqual(kwargs['total_sightings'], 2)

    @patch('app.render_template')
    @patch('app.requests.get')
    def test_unknown_howmany_gives_none_total(self, mock_get, mock_render):
        data = [{'comName': 'Dark-eyed Junco', 'obsDt': '2026-04-20 09:00',
                 'locName': 'The Ramble', 'subId': 'S333', 'howMany': None}]
        mock_get.return_value = MagicMock(json=MagicMock(return_value=data))
        mock_render.return_value = ''
        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(
                40.71, -74.00, loc_id='L123456', location='New York')
        _, kwargs = mock_render.call_args
        junco = kwargs['species_data'][0]
        self.assertIsNone(junco['total'],
                          "Species with no howMany should have total=None, not 0 or 1")

    @patch('app.render_template')
    @patch('app._fetch_all_obs_for_species')
    @patch('app.requests.get')
    def test_two_step_geo_gives_multiple_records(self, mock_get, mock_fetch, mock_render):
        """Index call identifies species, per-species fetch returns all checklists grouped correctly."""
        mock_render.return_value = ''
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'American Robin', 'speciesCode': 'amerob',
             'obsDt': '2026-04-20 08:00', 'locName': 'Central Park',
             'subId': 'S111', 'howMany': 3, 'lat': 40.78, 'lng': -73.96},
        ]))

        def fetch_side_effect(species_code, lat, lng, dist, back, headers):
            if species_code == 'amerob':
                return [
                    {'comName': 'American Robin', 'obsDt': '2026-04-20 08:00',
                     'locName': 'Central Park', 'subId': 'S111111111', 'howMany': 3},
                    {'comName': 'American Robin', 'obsDt': '2026-04-18 07:30',
                     'locName': 'Prospect Park', 'subId': 'S222222222', 'howMany': 5},
                ]
            return []

        mock_fetch.side_effect = fetch_side_effect

        with ebird_app.app.test_request_context():
            ebird_app.results_from_coordinates(40.71, -74.00, location='New York')

        _, kwargs = mock_render.call_args
        species_data = kwargs['species_data']
        self.assertEqual(len(species_data), 1)
        robin = species_data[0]
        self.assertEqual(robin['name'], 'American Robin')
        self.assertEqual(len(robin['records']), 2,
                         f"Expected 2 records from 2 checklists, got {len(robin['records'])}")
        self.assertEqual(robin['total'], 8,
                         f"Expected total=8 (3+5), got {robin['total']}")


class TestMapFunction(unittest.TestCase):
    """Verify get_species_sightings_at_coordinates URL strategy and tuple structure."""

    @patch('app._fetch_all_obs_for_species')
    @patch('app.requests.get')
    def test_no_filter_calls_geo_index_then_per_species(self, mock_get, mock_fetch):
        """No species/loc_id: geo/recent index called, then per-species expansion."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'American Robin', 'speciesCode': 'amerob',
             'obsDt': '2026-04-20 08:00', 'locName': 'Central Park',
             'subId': 'S111', 'howMany': 3, 'lat': 40.78, 'lng': -73.96},
        ]))
        mock_fetch.return_value = []
        ebird_app.get_species_sightings_at_coordinates((40.71, -74.00))
        index_url = mock_get.call_args[0][0]
        self.assertIn('/data/obs/geo/recent', index_url)
        self.assertNotIn('/ref/hotspot/geo', index_url)
        self.assertNotIn('notable', index_url)
        self.assertTrue(mock_fetch.called)

    @patch('app._fetch_all_obs_for_species')
    @patch('app.requests.get')
    def test_two_step_returns_coordinate_tuples(self, mock_get, mock_fetch):
        """Per-species results are returned as (lat, lng, comName, date, howMany, subId) tuples."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'American Robin', 'speciesCode': 'amerob',
             'obsDt': '2026-04-20 08:00', 'locName': 'Central Park',
             'subId': 'S111', 'howMany': 3, 'lat': 40.78, 'lng': -73.96},
        ]))
        mock_fetch.return_value = [
            {'comName': 'American Robin', 'obsDt': '2026-04-20 08:00',
             'locName': 'Central Park', 'subId': 'S111111111',
             'howMany': 3, 'lat': 40.78, 'lng': -73.96},
            {'comName': 'American Robin', 'obsDt': '2026-04-18 07:30',
             'locName': 'Prospect Park', 'subId': 'S222222222',
             'howMany': 5, 'lat': 40.66, 'lng': -73.97},
        ]
        result = ebird_app.get_species_sightings_at_coordinates((40.71, -74.00))
        self.assertEqual(len(result), 2)
        lats = {r[0] for r in result}
        self.assertIn(40.78, lats)
        self.assertIn(40.66, lats)
        self.assertTrue(all(r[2] == 'American Robin' for r in result))

    @patch('app._fetch_all_obs_for_species')
    @patch('app.requests.get')
    def test_notable_uses_notable_index_then_expands(self, mock_get, mock_fetch):
        """notable=True: notable endpoint used as index, then per-species expansion."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'Painted Bunting', 'speciesCode': 'painbu',
             'obsDt': '2026-04-20 08:00', 'locName': 'Central Park',
             'subId': 'S111', 'howMany': 1, 'lat': 40.78, 'lng': -73.96},
        ]))
        mock_fetch.return_value = [
            {'comName': 'Painted Bunting', 'obsDt': '2026-04-20 08:00',
             'locName': 'Central Park', 'subId': 'S111', 'howMany': 1,
             'lat': 40.78, 'lng': -73.96},
        ]
        result = ebird_app.get_species_sightings_at_coordinates((40.71, -74.00), notable=True)
        self.assertEqual(mock_get.call_count, 1)
        called_url = mock_get.call_args[0][0]
        self.assertIn('/data/obs/geo/recent/notable', called_url)
        self.assertTrue(mock_fetch.called)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][2], 'Painted Bunting')

    @patch('app.requests.get')
    def test_obs_missing_coords_excluded(self, mock_get):
        """Observations with lat=None or lng=None are dropped; valid ones are kept."""
        mock_get.return_value = MagicMock(json=MagicMock(return_value=[
            {'comName': 'American Robin', 'obsDt': '2026-04-20 08:00',
             'locName': 'Private', 'subId': 'S111', 'howMany': 3,
             'lat': None, 'lng': -73.96},
            {'comName': 'Dark-eyed Junco', 'obsDt': '2026-04-20 08:00',
             'locName': 'Central Park', 'subId': 'S222', 'howMany': 2,
             'lat': 40.78, 'lng': -73.96},
        ]))
        result = ebird_app.get_species_sightings_at_coordinates(
            (40.71, -74.00), loc_id='L123456')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][2], 'Dark-eyed Junco')

    @patch('app.requests.get')
    def test_api_error_response_does_not_crash(self, mock_get):
        """If eBird returns an error JSON dict, _fetch_all_obs_for_species returns [] safely."""
        result = ebird_app._fetch_all_obs_for_species(
            'amerob', 40.71, -74.00, 25, 14,
            headers={'X-eBirdApiToken': 'test'}
        )
        # We can't easily mock inside the helper in isolation, so test the isinstance guard:
        # Simulate what happens when the helper receives a dict response.
        mock_get.return_value = MagicMock(json=MagicMock(return_value={'errors': ['unauthorized']}))
        result = ebird_app._fetch_all_obs_for_species(
            'amerob', 40.71, -74.00, 25, 14,
            headers={'X-eBirdApiToken': 'test'}
        )
        self.assertEqual(result, [], "Non-list API response must return empty list, not dict")


class TestMapRendering(unittest.TestCase):
    def test_pins_render_with_clustering(self):
        """Each species gets its own MarkerCluster; markers render into the HTML."""
        fake_locations = [
            (40.78, -73.96, 'American Robin', 'Apr 20, 2026', 3, 'S111'),
            (40.66, -73.97, 'Dark-eyed Junco', 'Apr 18, 2026', 2, 'S222'),
        ]
        map_obj, species_cluster_vars = ebird_app.create_map_with_pins(fake_locations, (40.71, -74.00))
        html = map_obj.get_root().render()
        # Folium JSON-encodes marker HTML inside JS, so quotes are escaped
        self.assertIn('data-species=\\"American Robin\\"', html)
        self.assertIn('data-species=\\"Dark-eyed Junco\\"', html)
        self.assertIn('markerClusterGroup', html)
        # Each species has its own cluster entry
        self.assertIn('American Robin', species_cluster_vars)
        self.assertIn('Dark-eyed Junco', species_cluster_vars)
        self.assertNotEqual(species_cluster_vars['American Robin'], species_cluster_vars['Dark-eyed Junco'])


if __name__ == '__main__':
    unittest.main()
